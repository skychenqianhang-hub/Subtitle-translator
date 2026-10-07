"""「让 AI 生成词表」自检：解析模型返回、补全模式合并、费用估算、对话框流程（假的生成函数，不花钱）。

运行：python -m tests.test_glossary_gen
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["APPDATA"] = tempfile.mkdtemp(prefix="subtranslator_test_")

from app.config import Config  # noqa: E402
from app.core.errors import UserFacingError  # noqa: E402
from app.core.profiles.generate import (  # noqa: E402
    GenerateRequest, GlossaryDraft, estimate_cost_usd, output_schema, parse_draft, system_prompt,
    user_prompt,
)

SAMPLE = {
    "description": "英雄联盟：英雄、装备、地图术语",
    "asr_prompt": ["Ahri", "Yasuo", "Baron"],
    "rows": [
        {"en": "Ahri", "ja": "アーリ", "zh-Hans": "阿狸", "zh-Hant": "阿璃", "source": "https://example.com/ahri", "confidence": "official"},
        {"en": "Baron Nashor", "ja": "バロン", "zh-Hans": "纳什男爵", "zh-Hant": "巴龍", "source": "https://example.com/baron", "confidence": "community"},
        {"en": "gank", "ja": "", "zh-Hans": "抓人", "zh-Hant": "", "source": "", "confidence": "unsure"},
        {"en": "", "ja": "", "zh-Hans": "", "zh-Hant": "", "source": "", "confidence": "official"},
    ],
    "sources": ["https://example.com/ahri", "https://example.com/baron"],
}


def main() -> int:
    req = GenerateRequest(domain="英雄联盟", languages=["en", "ja", "zh-Hans", "zh-Hant"], max_terms=50)
    # 1. 输出格式与提示词
    schema = output_schema(req.languages)
    props = schema["properties"]["rows"]["items"]["properties"]
    assert set(props) == {"en", "ja", "zh-Hans", "zh-Hant", "source", "confidence"}
    assert schema["properties"]["rows"]["items"]["additionalProperties"] is False
    sp = system_prompt(req)
    assert "不要自己编造" in sp and "最多 12 次" in sp and "最多 50 行" in sp and "web_fetch" in sp
    assert "最多 8 次" in system_prompt(GenerateRequest(domain="x", languages=["en", "ja"], max_searches=8))
    assert "英雄联盟" in user_prompt(req)
    low, high = estimate_cost_usd("claude-sonnet-5-5", 120)
    assert 0.1 < low < high < 2.0, (low, high)
    assert estimate_cost_usd("claude-sonnet-5-5", 120, 8)[1] < high < estimate_cost_usd("claude-sonnet-5-5", 120, 20)[1]
    print("提示词 / 格式 / 估价：OK", round(low, 2), round(high, 2))

    # 2. 解析：空行丢掉，把握标注保留
    draft = parse_draft(json.dumps(SAMPLE, ensure_ascii=False), req)
    assert len(draft.rows) == 3 and draft.rows[0].terms == {"en": "Ahri", "ja": "アーリ", "zh-Hans": "阿狸", "zh-Hant": "阿璃"}
    assert draft.rows[2].terms == {"en": "gank", "zh-Hans": "抓人"} and draft.rows[2].confidence == "unsure"
    assert draft.asr_prompt == ["Ahri", "Yasuo", "Baron"] and draft.description.startswith("英雄联盟")
    draft.model, draft.searches, draft.input_tokens, draft.output_tokens = "claude-sonnet-5-5", 10, 40000, 6000
    assert abs(draft.cost_usd() - (0.10 + 0.08 + 0.06)) < 1e-6, draft.cost_usd()
    draft.cache_write_tokens, draft.cache_read_tokens = 20000, 200000
    assert abs(draft.cost_usd() - (0.10 + 0.08 + 0.06 + 0.05 + 0.04)) < 1e-6, draft.cost_usd()
    try:
        parse_draft("not json", req)
        raise AssertionError
    except UserFacingError:
        pass
    print("解析：OK")

    # 3. 补全模式：只填空格，不改已有的、不加新行
    existing = [{"en": "Ahri", "zh-Hans": "阿狸"}, {"en": "Yasuo", "zh-Hans": "亚索"}]
    req2 = GenerateRequest(domain="英雄联盟", languages=["en", "ja", "zh-Hans"], existing_rows=existing)
    filled = parse_draft(json.dumps({"description": "", "asr_prompt": [], "sources": [], "rows": [
        {"en": "Ahri", "ja": "アーリ", "zh-Hans": "阿狸（改了）", "source": "s", "confidence": "official"},
        {"en": "Teemo", "ja": "ティーモ", "zh-Hans": "提莫", "source": "", "confidence": "official"},
    ]}, ensure_ascii=False), req2)
    assert [d.terms for d in filled.rows] == [{"en": "Ahri", "zh-Hans": "阿狸", "ja": "アーリ"}, {"en": "Yasuo", "zh-Hans": "亚索"}], [d.terms for d in filled.rows]
    assert "补这些行里空着的语言格" in user_prompt(req2)
    print("补全模式：OK")

    # 4. 对话框：假生成函数 → 预览 → 删掉没把握的 → 加进场景页的术语表
    from PySide6.QtWidgets import QApplication, QDialog
    from app.core.profiles.store import ProfileStore
    from app.ui.profiles_page import ProfilesPage
    app = QApplication.instance() or QApplication(sys.argv)
    cfg = Config(anthropic_api_key="sk-ant-test", translate_provider="openai", translate_model="gpt-6.1-sol")
    store = ProfileStore(Path(tempfile.mkdtemp()))
    page = ProfilesPage(store, cfg)
    page.reload_tree(select="游戏")
    before = len(page.glossary.rows())
    calls: list[GenerateRequest] = []

    models: list[str] = []

    def fake_generate(cfg_, req_, model=None, progress=lambda s: None):
        calls.append(req_)
        models.append(model)
        progress("假装在查")
        d = parse_draft(json.dumps(SAMPLE, ensure_ascii=False), req_)
        d.model, d.searches, d.input_tokens, d.output_tokens = "gpt-6.1-sol", 9, 30000, 5000
        return d

    from PySide6.QtCore import QTimer

    def drive() -> None:
        dlg = page._generate_dialog
        assert dlg.domain.text() == "游戏", dlg.domain.text()
        assert "$" in dlg.estimate.text() and not dlg.accept_button.isEnabled()
        dlg.domain.setText("英雄联盟")
        dlg.lang_checks["ko"].setChecked(False)
        assert dlg.model.currentData() == "claude-sonnet-5-5", "主页用 GPT 时也应默认 Claude Sonnet"
        assert dlg.budget.currentData() == "medium"
        dlg.budget.setCurrentIndex(dlg.budget.findData("low"))
        dlg.cfg.anthropic_api_key = ""
        dlg.start()
        assert "Anthropic" in dlg.status.text() and dlg.draft is None, "没有 Anthropic Key 不应开始"
        dlg.cfg.anthropic_api_key = "sk-ant-test"
        dlg.start()
        deadline = time.time() + 10
        while dlg.draft is None and time.time() < deadline:
            app.processEvents()
            time.sleep(0.02)
        assert dlg.draft is not None, dlg.status.text()
        assert dlg.table.rowCount() == 3 and dlg.accept_button.isEnabled()
        assert "没把握" in dlg.summary.text() and "$" in dlg.status.text()
        dlg._remove_unsure()
        assert dlg.table.rowCount() == 2
        dlg._accept()

    QTimer.singleShot(0, drive)
    page._generate_glossary(generator=fake_generate)
    assert calls and calls[0].domain == "英雄联盟" and "ko" not in calls[0].languages and calls[0].max_terms == 120
    assert calls[0].max_searches == 8
    assert models == ["claude-sonnet-5-5"], models
    rows = page.glossary.rows()
    assert len(rows) == before + 2, (len(rows), before)
    assert {"en": "Ahri", "ja": "アーリ", "zh-Hans": "阿狸", "zh-Hant": "阿璃"} in rows
    assert "Ahri" in page.asr_prompt.toPlainText() and "Baron" in page.asr_prompt.toPlainText()
    assert "新增 2 条" in page.status.text(), page.status.text()
    page.save()
    assert store.resolve("游戏").glossary_for("en", "zh-Hant")["Ahri"] == "阿璃"
    assert store.get("游戏").description.startswith("所有游戏场景"), "原有说明不应被覆盖"
    # 根场景没有默认领域；没有 cfg 时按钮隐藏
    page.reload_tree(select="通用")
    page2 = ProfilesPage(store)
    assert not page2.generate_button.isVisibleTo(page2) and page.generate_button.isVisibleTo(page)
    print("对话框流程：OK")
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
