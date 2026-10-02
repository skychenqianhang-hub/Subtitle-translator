"""SRT 字幕文件的生成与读取。"""
from __future__ import annotations

from pathlib import Path

from app.core.subtitle.models import SubtitleLine


def fmt_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    ms = int(round(seconds * 1000))
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def line_text(ln: SubtitleLine, mode: str) -> str:
    """mode：bilingual（原文一行 + 译文一行）/ target_only / source_only。"""
    if mode == "source_only":
        return ln.source
    if mode == "target_only":
        return ln.target or ln.source
    if ln.target:
        return f"{ln.source}\n{ln.target}"
    return ln.source


def to_srt(lines: list[SubtitleLine], mode: str = "bilingual") -> str:
    blocks: list[str] = []
    n = 0
    for ln in lines:
        text = line_text(ln, mode).strip()
        if not text:
            continue
        n += 1
        end = max(ln.end, ln.start + 0.5)
        blocks.append(f"{n}\n{fmt_time(ln.start)} --> {fmt_time(end)}\n{text}\n")
    return "\n".join(blocks)


def write_srt(path: str | Path, lines: list[SubtitleLine], mode: str = "bilingual") -> Path:
    p = Path(path)
    p.write_text(to_srt(lines, mode), encoding="utf-8-sig")
    return p


def default_srt_path(media_path: str | Path, mode: str, target_language: str) -> Path:
    """字幕默认存在视频旁边，和视频同名。
    双语：xxx.ja+zh.srt 这种带语言的后缀会让播放器识别混乱，所以统一用 xxx.srt；
    仅原文用 xxx.orig.srt，避免覆盖已有的翻译字幕。"""
    src = Path(media_path)
    if mode == "source_only":
        return src.with_suffix(".orig.srt")
    return src.with_suffix(".srt")
