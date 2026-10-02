"""翻译提示词：各家翻译适配器共用，保证行为一致。"""
from __future__ import annotations

import json

from app.core.translate.base import TranslateRequest

LANG_NAMES = {
    "auto": "自动判断的语言",
    "ja": "日语", "en": "英语", "zh": "中文", "ko": "韩语",
    "zh-Hans": "简体中文", "zh-Hant": "繁体中文",
}


def lang_name(code: str) -> str:
    return LANG_NAMES.get(code, code)


def system_prompt(req: TranslateRequest) -> str:
    src = lang_name(req.source_language)
    tgt = lang_name(req.target_language)
    lines = [
        f"你是专业的字幕翻译。把{src}的语音识别文本翻译成{tgt}字幕。",
        "要求：",
        "1. 逐句翻译，输出的句数必须和输入完全一致，每句译文对应同编号的原文，不要合并、拆分或漏句。",
        "2. 字幕要简洁口语化，符合中文观众的表达习惯；单句过长时适当精简，但不能丢信息。",
        "3. 原文是语音识别结果，可能有错字、断句不佳；按上下文理解真实意思再翻。",
        "4. 「前文」只用来理解语境，不要翻译它。",
        "5. 只输出译文，不要解释，不要加引号。",
    ]
    if req.glossary:
        lines.append("6. 下面的术语表必须严格遵守（原文 → 译文；译文与原文相同表示保留不翻）：")
        for k, v in req.glossary.items():
            lines.append(f"   - {k} → {v}")
    if req.style:
        lines.append(f"翻译风格：{req.style}")
    if req.scene:
        lines.append(f"内容场景：{req.scene}")
    return "\n".join(lines)


def user_prompt(req: TranslateRequest) -> str:
    parts: list[str] = []
    if req.context:
        parts.append("【前文，仅供理解，不要翻译】")
        parts.extend(req.context)
        parts.append("")
    parts.append(f"【请翻译以下 {len(req.sentences)} 句，按编号返回】")
    for i, s in enumerate(req.sentences, 1):
        parts.append(f"{i}. {s}")
    return "\n".join(parts)


# 结构化输出：{"translations": ["...", "..."]}
OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "translations": {
            "type": "array",
            "items": {"type": "string"},
            "description": "译文列表，与输入句子一一对应、顺序一致",
        }
    },
    "required": ["translations"],
    "additionalProperties": False,
}


def parse_translations(text: str, expected: int) -> list[str]:
    """解析模型返回。优先 JSON；失败再按「1. xxx」逐行解析。长度不符会抛 ValueError。"""
    text = text.strip()
    try:
        data = json.loads(text)
        items = data["translations"] if isinstance(data, dict) else data
        if isinstance(items, list) and len(items) == expected:
            return [str(x).strip() for x in items]
    except (json.JSONDecodeError, KeyError, TypeError):
        pass
    import re
    numbered = re.findall(r"^\s*(\d+)[.、．:：]\s*(.*)$", text, flags=re.M)
    if numbered:
        by_idx = {int(n): t.strip() for n, t in numbered}
        if len(by_idx) == expected and all(i in by_idx for i in range(1, expected + 1)):
            return [by_idx[i] for i in range(1, expected + 1)]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if len(lines) == expected:
        return lines
    raise ValueError(f"译文句数不对：期望 {expected} 句，实际解析到 {len(numbered) or len(lines)} 句")
