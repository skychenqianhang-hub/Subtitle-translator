"""ASS 字幕生成：烧进视频时用，可以分别控制原文和译文的样式。"""
from __future__ import annotations

import re
from pathlib import Path

from app.core.subtitle.models import SubtitleLine

# 字号档位 → 译文字号（以 PlayResY=360 为基准，烧进视频时会按画面高度等比缩放）
SIZE_PRESETS = {"small": 15, "medium": 18, "large": 22}
SIZE_LABELS = {"small": "小", "medium": "中", "large": "大"}
FONT = "Microsoft YaHei"
PLAY_W, PLAY_H, MARGIN_LR = 640, 360, 20
# 微软雅黑在 ASS 里一个汉字的实际宽度约为字号的 0.78 倍（字号指的是行高，不是字宽）
CJK_CHAR_WIDTH = 0.78

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


def to_ass(lines: list[SubtitleLine], mode: str = "bilingual", size: str = "medium") -> str:
    """mode：bilingual / target_only / source_only。size：small / medium / large。"""
    main = SIZE_PRESETS.get(size, SIZE_PRESETS["medium"])
    sub = max(12, int(main * 0.72))
    # 一行最多放多少个中文字：画面宽减去左右边距，除以字号
    main_chars = max(10, int((PLAY_W - 2 * MARGIN_LR) / (main * CJK_CHAR_WIDTH)))
    sub_chars = max(10, int((PLAY_W - 2 * MARGIN_LR) / (sub * CJK_CHAR_WIDTH)))
    margin_v = 12   # 离底边的距离（画面高 360 的 3%）
    source_margin_v = margin_v + int(main * 1.4)
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {PLAY_W}
PlayResY: {PLAY_H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Target,{FONT},{main},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.6,0.6,2,{MARGIN_LR},{MARGIN_LR},{margin_v},1
Style: Source,{FONT},{sub},&H00D8D8D8,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.3,0.5,2,{MARGIN_LR},{MARGIN_LR},{source_margin_v},1
Style: Single,{FONT},{main},&H00FFFFFF,&H000000FF,&H00000000,&H80000000,0,0,0,0,100,100,0,0,1,1.6,0.6,2,{MARGIN_LR},{MARGIN_LR},{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []

    def ev(layer: int, start: str, end: str, style: str, text: str, chars: int, margin: int = 0) -> str:
        wrapped = wrap_cjk(_esc(text), chars)
        events.append(f"Dialogue: {layer},{start},{end},{style},,0,0,{margin},,{wrapped}")
        return wrapped

    for ln in lines:
        start, end = _ass_time(ln.start), _ass_time(max(ln.end, ln.start + 0.5))
        if mode == "source_only":
            ev(0, start, end, "Single", ln.source, main_chars)
        elif mode == "target_only":
            ev(0, start, end, "Single", ln.target or ln.source, main_chars)
        elif ln.target:
            wrapped = ev(0, start, end, "Target", ln.target, main_chars)
            # 译文占几行，原文就往上抬几行，避免叠在一起
            target_lines = wrapped.count("\\N") + 1
            ev(1, start, end, "Source", ln.source, sub_chars, margin_v + int(main * 1.4 * target_lines))
        else:
            ev(0, start, end, "Single", ln.source, main_chars)
    return header + "\n".join(events) + "\n"


def write_ass(path: str | Path, lines: list[SubtitleLine], mode: str = "bilingual", size: str = "medium") -> Path:
    p = Path(path)
    p.write_text(to_ass(lines, mode, size), encoding="utf-8-sig")
    return p
