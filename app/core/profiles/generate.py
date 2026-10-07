"""让 AI 联网生成多语言词表。

用户填一句话描述领域（「英雄联盟」「电影《沙丘 2》」），模型用自带的联网搜索查官方资料，
整理成和场景术语表一样的多语言行，每行附来源网址和把握程度；另外给出识别提示词（专有名词）和一句场景说明。
结果只是「草稿」，由界面给用户预览、删改后才合并进场景。

用户要求这个功能固定用 Claude（Anthropic Messages API 自带联网搜索：tools=[{"type": "web_search_20260209"}]，
服务端执行，usage.server_tool_use.web_search_requests 计次）。计费（2026-10 官方价）：每次搜索 $0.01，另加正常的 token 费。
"""
from __future__ import annotations

from app.i18n import tr

import json
from dataclasses import dataclass, field
from typing import Callable

from app.config import Config, GLOSSARY_LANG_NAMES
from app.core.cost import TRANSLATE_PRICE_PER_MTOK
from app.core.errors import UserFacingError
from app.core.profiles.glossary import GLOSSARY_LANGS, Row, clean_row

SEARCH_PRICE_USD = 0.01                 # 每次联网搜索（抓取网页不另收费，只算 token）
MAX_SEARCHES = 20                       # 硬上限
SEARCH_BUDGETS = {"low": 8, "medium": 12, "high": 20}      # 界面上的「联网预算」：省钱 / 标准 / 充分
DEFAULT_SEARCH_BUDGET = "medium"

CONFIDENCE_LABELS = {"official": "官方", "community": "社区常用", "unsure": "没把握"}


@dataclass
class GenerateRequest:
    domain: str                                   # 用户的一句话描述
    languages: list[str]                          # 要填的列，例如 ["en", "ja", "zh-Hans", "zh-Hant"]
    max_terms: int = 120
    existing_rows: list[Row] = field(default_factory=list)   # 「补全空格」模式：只补这些行缺的格
    ui_language: str = "zh"                       # 说明文字用哪种语言写
    max_searches: int = SEARCH_BUDGETS[DEFAULT_SEARCH_BUDGET]


@dataclass
class DraftRow:
    terms: Row                                    # {lang: 词}
    source: str = ""                              # 来源网址
    confidence: str = "unsure"                    # official / community / unsure


@dataclass
class GlossaryDraft:
    rows: list[DraftRow]
    asr_prompt: list[str]
    description: str
    sources: list[str]
    searches: int = 0
    fetches: int = 0
    input_tokens: int = 0                         # 不含缓存的输入
    cache_write_tokens: int = 0                   # 写入缓存（1.25 倍价）
    cache_read_tokens: int = 0                    # 从缓存读（0.1 倍价）
    output_tokens: int = 0
    model: str = ""

    def cost_usd(self) -> float:
        pin, pout = TRANSLATE_PRICE_PER_MTOK.get(self.model, (0.0, 0.0))
        tokens = (self.input_tokens * pin + self.cache_write_tokens * pin * 1.25 + self.cache_read_tokens * pin * 0.1
                  + self.output_tokens * pout) / 1_000_000
        return self.searches * SEARCH_PRICE_USD + tokens


def estimate_cost_usd(model: str, max_terms: int, max_searches: int = SEARCH_BUDGETS[DEFAULT_SEARCH_BUDGET]) -> tuple[float, float]:
    """给界面显示的大致费用区间（低、高）。

    2026-10-07 第一次实测（没开缓存、没限制回显）：20 次搜索、63 条 → 输入 33.8 万 token、输出 2.5 万、$1.13。
    之后加了提示缓存（服务端每轮搜索结果自动进缓存，后续轮次按 0.1 倍价读）、不回显搜索原文、思考档位调低，
    估法：每次搜索约 1.5 万 token，其中约 85% 走缓存读；输出每条约 250 token。低 = 用掉一半预算，高 = 用满。
    """
    pin, pout = TRANSLATE_PRICE_PER_MTOK.get(model, (2.0, 10.0))

    def cost(searches: int) -> float:
        per_search = 15_000
        token_cost = (searches * per_search * (0.15 + 0.85 * 0.1) + 10_000) * pin + max_terms * 250 * pout
        return searches * SEARCH_PRICE_USD + token_cost / 1_000_000

    return cost(max(1, max_searches // 2)), cost(max_searches)


# ---------------------------------------------------------------- 提示词与输出格式
def output_schema(languages: list[str]) -> dict:
    row_props = {lang: {"type": "string", "description": f"{GLOSSARY_LANG_NAMES.get(lang, lang)}写法；查不到就留空字符串"}
                 for lang in languages}
    row_props["source"] = {"type": "string", "description": "这一行主要依据的网址；没有就留空"}
    row_props["confidence"] = {"type": "string", "enum": ["official", "community", "unsure"],
                               "description": "official=官方页面确认；community=社区 / 媒体常用说法；unsure=没查到依据"}
    return {
        "type": "object",
        "properties": {
            "description": {"type": "string", "description": "一句话场景说明"},
            "asr_prompt": {"type": "array", "items": {"type": "string"},
                           "description": "专有名词（人名、地名、物品名）原文，给语音识别当提示，最多 60 个"},
            "rows": {
                "type": "array",
                "items": {"type": "object", "properties": row_props,
                          "required": list(row_props.keys()), "additionalProperties": False},
            },
            "sources": {"type": "array", "items": {"type": "string"}, "description": "主要参考的网址列表"},
        },
        "required": ["description", "asr_prompt", "rows", "sources"],
        "additionalProperties": False,
    }


def system_prompt(req: GenerateRequest) -> str:
    langs = "、".join(GLOSSARY_LANG_NAMES.get(lang, lang) for lang in req.languages)
    lines = [
        "你是字幕翻译软件的术语表编辑。任务：为用户给的领域整理一张多语言术语对照表，供翻译模型在翻字幕时遵守。",
        f"需要的语言列：{langs}。每一行是同一个概念在各语言里的写法，同一语言只写一个最通行的写法。",
        "工作方式：",
        "0. 必须联网核对，不要凭记忆填写。每一行的 source 必须是你这次用 web_search / web_fetch 实际看到的网址；"
        "没有查证过的行一律标 unsure 并把 source 留空。凭记忆写出来的「官方译名」经常是错的，查证是这项工作的全部意义。",
        "1. 先联网查官方资料（官网各语言页面、官方更新公告、片方 / 发行方官网、各语言维基百科），再查该语言玩家 / 观众的常用说法。",
        "   省钱的查法：优先找「一页列出全部名字」的页面（例如官网的角色 / 地图 / 物品一览页、维基的列表页），用 web_fetch 抓整页读，一页就能拿到几十个词；"
        "web_search 只用来找这些页面在哪里、以及核对个别拿不准的词。",
        "2. 优先收录：人名、角色名、地名、组织名、物品 / 技能 / 道具名、该领域特有的行话缩写——也就是机器翻译容易翻错或翻得不一致的词。普通词汇不要。",
        "3. 每一行写明主要依据的网址，并标注把握：official（官方页面确认）/ community（社区或媒体常用）/ unsure（没查到依据）。",
        "4. 每一个语言列都要专门去找至少一个该语言的一览页（官网找不到就用该语言的维基百科 / 社区百科，标 community），不要让某一列整列空着；"
        "单个词实在查不到就留空，绝对不要自己编造或音译；宁可留空也不要猜。",
        "5. 繁体中文优先用台湾 / 香港官方或通行写法，不要只是把简体字转成繁体字。",
        f"6. 最多 {req.max_terms} 行，按重要程度排序。",
        "7. 另外给出：一句话场景说明；识别提示词（专有名词的原文写法，给语音识别用，最多 60 个）；主要参考网址列表。",
        f"8. 联网搜索最多 {req.max_searches} 次、抓取网页最多 {req.max_searches} 次，把每次都用在刀刃上。",
        "说明文字（description）用" + {"zh": "简体中文", "ja": "日语", "en": "英语"}.get(req.ui_language, "简体中文") + "写。",
    ]
    return "\n".join(lines)


def user_prompt(req: GenerateRequest) -> str:
    if req.existing_rows:
        parts = [f"领域：{req.domain}", "", "下面是已有的术语表，请只补这些行里空着的语言格（不要新增行、不要改已有的格）："]
        for r in req.existing_rows:
            parts.append(json.dumps({lang: r.get(lang, "") for lang in req.languages}, ensure_ascii=False))
        return "\n".join(parts)
    return f"领域：{req.domain}\n请先联网查资料（抓取官方的一览页），再整理这个领域的多语言术语表。"


def parse_draft(text: str, req: GenerateRequest) -> GlossaryDraft:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise UserFacingError(tr("模型返回的内容不是有效的表格数据：{0}", e)) from e
    rows: list[DraftRow] = []
    for item in data.get("rows") or []:
        if not isinstance(item, dict):
            continue
        terms = clean_row({k: v for k, v in item.items() if k in GLOSSARY_LANGS})
        if not terms:
            continue
        conf = str(item.get("confidence") or "unsure")
        rows.append(DraftRow(terms=terms, source=str(item.get("source") or "").strip(),
                             confidence=conf if conf in CONFIDENCE_LABELS else "unsure"))
    if req.existing_rows:
        rows = _merge_fill(req.existing_rows, rows)
    prompt = [str(x).strip() for x in (data.get("asr_prompt") or []) if str(x).strip()][:60]
    sources = [str(x).strip() for x in (data.get("sources") or []) if str(x).strip()]
    return GlossaryDraft(rows=rows, asr_prompt=prompt, description=str(data.get("description") or "").strip(),
                         sources=sources)


def _merge_fill(existing: list[Row], drafted: list[DraftRow]) -> list[DraftRow]:
    """补全模式：只把模型填的空格合进已有行，已有的格一律不动。"""
    out: list[DraftRow] = []
    for base in existing:
        match = next((d for d in drafted if any(d.terms.get(lang) == base.get(lang) for lang in base)), None)
        merged = dict(base)
        if match:
            for lang, term in match.terms.items():
                if term and not merged.get(lang):
                    merged[lang] = term
        out.append(DraftRow(terms=merged, source=match.source if match else "",
                            confidence=match.confidence if match else "unsure"))
    return out


# ---------------------------------------------------------------- 两家接口
ProgressCb = Callable[[str], None]


GENERATE_MODELS = [                       # 用户要求这个功能固定用 Claude（2026-10-07）
    ("claude-sonnet-5-5", "Claude Sonnet 5.5：推荐，$2/$10"),
    ("claude-opus-5-5", "Claude Opus 5.5：质量更高，$4/$20，约贵一倍"),
]
DEFAULT_GENERATE_MODEL = "claude-sonnet-5-5"


def generate_glossary(cfg: Config, req: GenerateRequest, model: str | None = None,
                      progress: ProgressCb = lambda s: None) -> GlossaryDraft:
    if not req.domain.strip():
        raise UserFacingError(tr("请先写一句话描述这个领域。"))
    return _generate_anthropic(cfg, req, model or DEFAULT_GENERATE_MODEL, progress)


def _generate_anthropic(cfg: Config, req: GenerateRequest, model: str, progress: ProgressCb,
                        _retried: bool = False) -> GlossaryDraft:
    if not cfg.has_anthropic_key():
        raise UserFacingError(tr("还没有填 Anthropic 的 API Key。请到右上角「设置 → API Key」填写。"))
    import anthropic
    client = anthropic.Anthropic(api_key=cfg.anthropic_api_key, timeout=900.0, max_retries=1)
    progress(tr("正在联网查资料并整理（通常要一到三分钟）……"))
    budget = max(1, min(req.max_searches, MAX_SEARCHES))
    user = user_prompt(req)
    if _retried:
        user += "\n\n注意：上一次你没有使用 web_search / web_fetch 就直接作答了。这次必须先联网抓取官方页面核对，再输出。"
    messages: list[dict] = [{"role": "user", "content": user}]
    draft_usage = {"searches": 0, "fetches": 0, "input": 0, "cache_write": 0, "cache_read": 0, "output": 0}
    resp = None
    for _ in range(6):                      # 搜索轮次多时服务端会先停一下（pause_turn），把结果接回去继续
        with client.messages.stream(
            model=model,
            max_tokens=32000,
            system=system_prompt(req),
            messages=messages,
            # 省钱三件套：
            # 1) 开提示缓存：有了 cache_control，服务端每轮搜索 / 抓取结果会自动进缓存，后面几轮按 0.1 倍价读，
            #    不然每多搜一次，前面所有结果都要按全价重算一遍（第一次实测 20 次搜索吃了 34 万 token）
            # 2) response_inclusion=excluded：不把搜索 / 网页原文回显到输出里（输出价是输入的 5 倍）
            # 3) 抓网页不另收费，只收 token；限制每页最多 2 万 token
            cache_control={"type": "ephemeral"},
            tools=[
                {"type": "web_search_20260318", "name": "web_search", "max_uses": budget,
                 "response_inclusion": "excluded"},
                {"type": "web_fetch_20260318", "name": "web_fetch", "max_uses": budget,
                 "max_content_tokens": 20000, "response_inclusion": "excluded"},
            ],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": output_schema(req.languages)}},
        ) as stream:
            resp = stream.get_final_message()
        u = getattr(resp, "usage", None)
        if u is not None:
            draft_usage["input"] += int(getattr(u, "input_tokens", 0) or 0)
            draft_usage["cache_write"] += int(getattr(u, "cache_creation_input_tokens", 0) or 0)
            draft_usage["cache_read"] += int(getattr(u, "cache_read_input_tokens", 0) or 0)
            draft_usage["output"] += int(getattr(u, "output_tokens", 0) or 0)
            st = getattr(u, "server_tool_use", None)
            if st is not None:
                draft_usage["searches"] += int(getattr(st, "web_search_requests", 0) or 0)
                draft_usage["fetches"] += int(getattr(st, "web_fetch_requests", 0) or 0)
        if resp.stop_reason == "refusal":
            raise UserFacingError(tr("Claude 拒绝处理这个领域（触发了安全策略）。可以换 GPT 试试。"))
        if resp.stop_reason != "pause_turn":
            break
        messages = [messages[0], {"role": "assistant", "content": resp.content}]
        progress(tr("资料较多，继续查……（已搜索 {0} 次）", draft_usage["searches"]))
    text = next((b.text for b in (resp.content if resp else []) if getattr(b, "type", "") == "text"), "")
    if not text:
        raise UserFacingError(tr("模型没有返回表格内容。"))
    draft = parse_draft(text, req)
    if draft_usage["searches"] + draft_usage["fetches"] == 0:
        if not _retried:
            # 模型觉得自己「都知道」就没上网——第二次实测就遇到了：0 次搜索、来源全是凭记忆写的。再要求一次。
            progress(tr("模型没有联网核对，重新要求一次……"))
            return _generate_anthropic(cfg, req, model, progress, _retried=True)
        for d in draft.rows:                 # 还是不联网：全部标「没把握」，来源清空，别让用户误以为查过
            d.confidence, d.source = "unsure", ""
        draft.sources = []
    draft.searches, draft.fetches = draft_usage["searches"], draft_usage["fetches"]
    draft.input_tokens, draft.output_tokens = draft_usage["input"], draft_usage["output"]
    draft.cache_write_tokens, draft.cache_read_tokens = draft_usage["cache_write"], draft_usage["cache_read"]
    draft.model = model
    return draft
