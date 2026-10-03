"""文档输出自检。运行：python -m tests.test_document"""
from __future__ import annotations

import sys

from app.core.subtitle.document import default_document_path, paragraphs, to_document
from app.core.subtitle.models import SubtitleLine


def main() -> int:
    lines = [
        SubtitleLine(0.0, 1.5, "みなさんこんにちは。", "大家好。"),
        SubtitleLine(1.9, 4.3, "今日はランクマッチをやっていきます。", "今天来打排位赛。"),
        SubtitleLine(8.0, 10.0, "よし、ゲームが始まりました。", "好，游戏开始了。"),   # 停顿 3.7 秒 → 新段落
    ]
    src = paragraphs(lines, "source")
    assert src == ["みなさんこんにちは。今日はランクマッチをやっていきます。", "よし、ゲームが始まりました。"], src
    tgt = paragraphs(lines, "target")
    assert tgt == ["大家好。今天来打排位赛。", "好，游戏开始了。"], tgt
    en = paragraphs([SubtitleLine(0, 1, "Hello there.", ""), SubtitleLine(1, 2, "How are you?", "")], "source")
    assert en == ["Hello there. How are you?"], en

    doc = to_document(lines, "bilingual", title="测试", source_name="原文（日语）", target_name="译文（简体中文）")
    assert doc.startswith("测试\n\n【原文（日语）】\n\nみなさん")
    assert "【译文（简体中文）】\n\n大家好。今天来打排位赛。\n\n好，游戏开始了。" in doc
    assert "-->" not in doc
    only_t = to_document(lines, "target_only")
    assert "【" not in only_t and "大家好" in only_t and "こんにちは" not in only_t
    only_s = to_document(lines, "source_only")
    assert "【" not in only_s and "こんにちは" in only_s and "大家好" not in only_s
    assert default_document_path("a/b.mp4", "bilingual", "简体中文").name == "b.原文+译文.txt"
    assert default_document_path("a/b.mp4", "target_only", "简体中文").name == "b.简体中文译文.txt"
    print("文档输出：OK")
    print("全部通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
