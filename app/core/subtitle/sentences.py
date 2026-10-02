"""把识别出来的碎片合并成完整句子，并把过长的句子拆开。

日语的否定、时态都在句尾，半句话翻译容易翻反，所以尽量以句号、问号等结尾为界。
"""
from __future__ import annotations

import re

from app.core.asr.base import Segment
from app.core.subtitle.models import SubtitleLine

_END_PUNCT = "。．.!！?？」』…"
_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def _is_cjk(text: str) -> bool:
    return bool(_CJK.search(text))


def _ends_sentence(text: str) -> bool:
    t = text.rstrip()
    return bool(t) and t[-1] in _END_PUNCT


def _join(a: str, b: str) -> str:
    if _is_cjk(a) or _is_cjk(b):
        return a.rstrip() + b.lstrip()
    return a.rstrip() + " " + b.lstrip()


def merge_into_sentences(
    segments: list[Segment],
    max_gap: float = 1.2,
    max_chars_cjk: int = 48,
    max_chars_latin: int = 110,
    max_duration: float = 8.0,
) -> list[SubtitleLine]:
    lines: list[SubtitleLine] = []
    cur: SubtitleLine | None = None
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if cur is None:
            cur = SubtitleLine(seg.start, seg.end, text)
            continue
        limit = max_chars_cjk if _is_cjk(cur.source) else max_chars_latin
        gap = seg.start - cur.end
        merged = _join(cur.source, text)
        too_long = len(merged) > limit or (seg.end - cur.start) > max_duration
        if _ends_sentence(cur.source) or gap > max_gap or too_long:
            lines.append(cur)
            cur = SubtitleLine(seg.start, seg.end, text)
        else:
            cur.source = merged
            cur.end = seg.end
    if cur is not None:
        lines.append(cur)
    return lines


def _pack(pieces: list[str], limit: int) -> list[str]:
    out: list[str] = []
    buf = ""
    for p in pieces:
        if not p:
            continue
        if buf and len(buf) + len(p) > limit:
            out.append(buf.strip())
            buf = p
        else:
            buf += p
    if buf.strip():
        out.append(buf.strip())
    return out


def split_sentences(text: str) -> list[str]:
    """按句末标点（。！？等）把一段文字拆成句子。"""
    # 全角句末标点后直接切；英文句号只在后面跟空格时切（避免把 3.5、Mr. 这类切断）
    pieces = [p for p in re.split(r"(?<=[。．!！?？])\s*|(?<=[.!?])\s+", text) if p and p.strip()]
    return pieces or [text]


def _split_text(text: str, limit: int) -> list[str]:
    """长文本先按句末标点拆成句子；仍超长的句子再按逗号拆。"""
    if len(text) <= limit:
        return [text]
    out: list[str] = []
    for sent in split_sentences(text):
        if len(sent) <= limit:
            out.append(sent.strip())
            continue
        out.extend(_pack(re.split(r"(?<=[、，,；;])", sent), limit))
    # 还是太长（没有标点）就硬切
    final: list[str] = []
    for s in out:
        while len(s) > limit * 1.5:
            final.append(s[:limit])
            s = s[limit:]
        final.append(s)
    return final


def split_long_lines(lines: list[SubtitleLine], max_chars_cjk: int = 48, max_chars_latin: int = 110) -> list[SubtitleLine]:
    """一条字幕里有多句话（没有时间戳的模型会整块返回）就按句拆开；过长的再按逗号拆。时间按长度比例分配。"""
    out: list[SubtitleLine] = []
    for ln in lines:
        limit = max_chars_cjk if _is_cjk(ln.source) else max_chars_latin
        parts = split_sentences(ln.source) if len(ln.source) <= limit else _split_text(ln.source, limit)
        parts = [p for p in parts if p.strip()]
        if len(parts) <= 1:
            out.append(ln)
            continue
        total = sum(len(p) for p in parts) or 1
        t = ln.start
        dur = ln.end - ln.start
        for p in parts:
            d = dur * len(p) / total
            out.append(SubtitleLine(t, t + d, p))
            t += d
    return out
