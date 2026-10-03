"""文档输出：把字幕整理成通顺的全文（原文一整段、译文一整段），存成 .txt，可以直接用记事本打开。"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.subtitle.models import SubtitleLine

_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")

# 两句之间停顿超过这么多秒，就另起一段
PARAGRAPH_GAP = 2.5


def _join(parts: list[str]) -> str:
    """中日韩文直接连，拉丁文用空格连。"""
    out = ""
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not out:
            out = p
        elif _CJK.search(out[-1:]) or _CJK.search(p[:1]):
            out += p
        else:
            out += " " + p
    return out


def paragraphs(lines: list[SubtitleLine], field: str) -> list[str]:
    """按长停顿分段，每段把句子连成一整段文字。field = "source" 或 "target"。"""
    paras: list[str] = []
    buf: list[str] = []
    prev_end: float | None = None
    for ln in lines:
        text = (ln.target if field == "target" else ln.source) or ""
        if field == "target" and not text:
            text = ln.source
        if prev_end is not None and ln.start - prev_end > PARAGRAPH_GAP and buf:
            paras.append(_join(buf))
            buf = []
        buf.append(text)
        prev_end = ln.end
    if buf:
        paras.append(_join(buf))
    return [p for p in paras if p]


def to_document(lines: list[SubtitleLine], mode: str, title: str = "",
                source_name: str = "原文", target_name: str = "译文") -> str:
    """mode：bilingual（原文整体 + 译文整体）/ target_only / source_only。"""
    blocks: list[str] = []
    if title:
        blocks.append(title)
        blocks.append("")
    if mode in ("bilingual", "source_only"):
        if mode == "bilingual":
            blocks.append(f"【{source_name}】")
            blocks.append("")
        blocks.extend(_with_blank_lines(paragraphs(lines, "source")))
    if mode == "bilingual":
        blocks.append("")
        blocks.append(f"【{target_name}】")
        blocks.append("")
    if mode in ("bilingual", "target_only"):
        blocks.extend(_with_blank_lines(paragraphs(lines, "target")))
    return "\n".join(blocks).rstrip() + "\n"


def _with_blank_lines(paras: list[str]) -> list[str]:
    out: list[str] = []
    for i, p in enumerate(paras):
        if i:
            out.append("")
        out.append(p)
    return out


def default_document_path(media_path: str | Path, mode: str, target_name: str) -> Path:
    src = Path(media_path)
    tag = {"bilingual": "原文+译文", "source_only": "原文"}.get(mode, f"{target_name}译文")
    return src.with_name(f"{src.stem}.{tag}.txt")


def write_document(path: str | Path, lines: list[SubtitleLine], mode: str, title: str = "",
                   source_name: str = "原文", target_name: str = "译文") -> Path:
    p = Path(path)
    # 记事本用 \r\n 换行最稳；带 BOM 让旧版记事本也能正确识别 UTF-8
    text = to_document(lines, mode, title, source_name, target_name).replace("\n", "\r\n")
    p.write_text(text, encoding="utf-8-sig")
    return p
