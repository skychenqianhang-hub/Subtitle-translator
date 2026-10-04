"""字幕样式：字体、字号、颜色、描边、阴影、底框、对齐、位置。译文和原文各一套。

所有尺寸以「画面高 360」为基准（和烧录用的 ASS 画布一致），显示和烧录时按实际画面等比缩放。
位置用百分比：x_pct 是锚点横向位置，y_pct 是文字块底边的纵向位置（100 = 画面最底）。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields

PLAY_W, PLAY_H = 640, 360
ALIGN_AN = {"left": 1, "center": 2, "right": 3}   # ASS \an：底部左 / 中 / 右


@dataclass
class TextStyle:
    font: str = "Microsoft YaHei"
    size: int = 18                 # 基准字号（画面高 360 时的像素）
    bold: bool = True
    italic: bool = False
    color: str = "#FFFFFF"
    outline_color: str = "#000000"
    outline: float = 1.6           # 描边粗细
    shadow: float = 0.6            # 阴影距离
    back_color: str = "#000000"
    back_alpha: int = 0            # 底框不透明度 0-100，0 = 不要底框
    align: str = "center"          # left / center / right
    x_pct: float = 50.0
    y_pct: float = 96.0
    visible: bool = True

    @classmethod
    def from_dict(cls, d: dict | None) -> "TextStyle":
        d = d or {}
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class SubtitleStyle:
    target: TextStyle = field(default_factory=TextStyle)
    source: TextStyle = field(default_factory=lambda: TextStyle(size=13, bold=False, color="#D8D8D8", outline=1.3,
                                                                 shadow=0.5, y_pct=88.0))

    def to_dict(self) -> dict:
        return {"target": asdict(self.target), "source": asdict(self.source)}

    @classmethod
    def from_dict(cls, d: dict | None) -> "SubtitleStyle":
        d = d or {}
        s = cls()
        if "target" in d:
            s.target = TextStyle.from_dict(d["target"])
        if "source" in d:
            s.source = TextStyle.from_dict(d["source"])
        return s

    @classmethod
    def from_legacy(cls, size: str = "medium", margin_pct: int = 3) -> "SubtitleStyle":
        """旧的「小 / 中 / 大 + 底边距」设置换算成样式。"""
        presets = {"small": 15, "medium": 18, "large": 22}
        main = presets.get(size, 18)
        s = cls()
        s.target.size = main
        s.target.y_pct = 100 - margin_pct
        s.source.size = max(12, int(main * 0.72))
        s.source.y_pct = s.target.y_pct - (main * 1.4) / PLAY_H * 100
        return s


PRESETS: dict[str, SubtitleStyle] = {
    "默认（白字黑边）": SubtitleStyle(),
    "黄字黑边": SubtitleStyle(target=TextStyle(color="#FFE34D", outline=1.8),
                          source=TextStyle(size=13, bold=False, color="#FFF2B3", outline=1.3, shadow=0.5, y_pct=88.0)),
    "黑底白字": SubtitleStyle(target=TextStyle(outline=0, shadow=0, back_alpha=70),
                          source=TextStyle(size=13, bold=False, color="#E6E6E6", outline=0, shadow=0, back_alpha=70, y_pct=88.0)),
    "大字": SubtitleStyle(target=TextStyle(size=24, y_pct=95.0),
                        source=TextStyle(size=16, bold=False, color="#D8D8D8", outline=1.3, shadow=0.5, y_pct=84.0)),
}


# ---------------------------------------------------------------- ASS 换算
def _ass_color(hex_color: str, transparency_pct: int = 0) -> str:
    """#RRGGBB + 透明度百分比（0 = 完全不透明）→ ASS 的 &HAABBGGRR（AA 00 = 不透明，FF = 全透明）。"""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    aa = int(round(255 * max(0, min(100, transparency_pct)) / 100))
    return f"&H{aa:02X}{b}{g}{r}".upper()


def ass_style_line(name: str, st: TextStyle) -> str:
    primary = _ass_color(st.color)
    outline = _ass_color(st.outline_color)
    if st.back_alpha > 0:
        border_style = 3          # 3 = 底框
        back = _ass_color(st.back_color, 100 - st.back_alpha)
        outline_w = max(2.0, st.outline)   # BorderStyle 3 时 Outline 是底框的内边距
        shadow = 0
    else:
        border_style = 1
        back = _ass_color("#000000", 50)
        outline_w = st.outline
        shadow = st.shadow
    return (f"Style: {name},{st.font},{st.size},{primary},&H000000FF,{outline},{back},"
            f"{-1 if st.bold else 0},{-1 if st.italic else 0},0,0,100,100,0,0,{border_style},"
            f"{outline_w:.2f},{shadow:.2f},{ALIGN_AN.get(st.align, 2)},0,0,0,1")


def ass_pos_tag(st: TextStyle) -> str:
    x = PLAY_W * st.x_pct / 100
    y = PLAY_H * st.y_pct / 100
    return f"{{\\an{ALIGN_AN.get(st.align, 2)}\\pos({x:.0f},{y:.0f})}}"


def chars_per_line(st: TextStyle) -> int:
    """一行最多放多少个汉字（按字宽 ≈ 0.78 字号估算），留 8% 边距。"""
    return max(8, int(PLAY_W * 0.92 / (st.size * 0.78)))
