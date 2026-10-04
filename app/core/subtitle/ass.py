"""ASS 字幕生成：烧进视频时用，按 SubtitleStyle 控制字体、颜色、描边、位置。"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.style import PLAY_H, PLAY_W, SubtitleStyle, TextStyle, ass_pos_tag, ass_style_line, chars_per_line

# 兼容旧接口：字号档位
SIZE_PRESETS = {"small": 15, "medium": 18, "large": 22}
SIZE_LABELS = {"small": "小", "medium": "中", "large": "大"}

_CJK = re.compile(r"[぀-ヿ㐀-鿿가-힯]")


def _ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0.0
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360_000)
    m, cs = divmod(cs, 6_000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _esc(text: str) -> str:
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def wrap_cjk(text: str, max_chars: int) -> str:
    """中日韩文字之间没有空格，渲染器不会自动换行，这里按字数手动换行，尽量在标点后断开。"""
    if not _CJK.search(text) or len(text) <= max_chars:
        return text
    n_lines = -(-len(text) // max_chars)
    target = -(-len(text) // n_lines)   # 每行目标字数，让各行长度均匀
    out: list[str] = []
    rest = text
    while len(rest) > max_chars:
        lo, hi = max(1, target - 8), min(len(rest) - 1, target + 8)
        cut = target
        for i in range(lo, hi):
            if rest[i - 1] in "，。、！？；：,.!?;:":
                cut = i
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return "\\N".join(out)


def to_ass(lines: list[SubtitleLine], mode: str = "bilingual", size: str = "medium", margin_pct: int = 3,
           style: SubtitleStyle | None = None) -> str:
    """mode：bilingual / target_only / source_only。
    style 为空时用旧的「字号档位 + 底边距」换算。"""
    st = style or SubtitleStyle.from_legacy(size, margin_pct)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
{ass_style_line("Target", st.target)}
{ass_style_line("Source", st.source)}

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []

    def ev(layer: int, start: str, end: str, name: str, ts: TextStyle, text: str) -> None:
        if not ts.visible or not text:
            return
        wrapped = wrap_cjk(_esc(text), chars_per_line(ts))
        events.append(f"Dialogue: {layer},{start},{end},{name},,0,0,0,,{ass_pos_tag(ts)}{wrapped}")

    for ln in lines:
        start, end = _ass_time(ln.start), _ass_time(max(ln.end, ln.start + 0.5))
        if mode == "source_only":
            ev(0, start, end, "Target", st.target, ln.source)
        elif mode == "target_only":
            ev(0, start, end, "Target", st.target, ln.target or ln.source)
        elif ln.target:
            ev(0, start, end, "Target", st.target, ln.target)
            ev(1, start, end, "Source", st.source, ln.source)
        else:
            ev(0, start, end, "Target", st.target, ln.source)
    return header + "\n".join(events) + "\n"


def write_ass(path: str | Path, lines: list[SubtitleLine], mode: str = "bilingual", size: str = "medium",
              margin_pct: int = 3, style: SubtitleStyle | None = None) -> Path:
    p = Path(path)
    p.write_text(to_ass(lines, mode, size, margin_pct, style), encoding="utf-8-sig")
    return p
