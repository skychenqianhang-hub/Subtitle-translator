"""第五轮 logo 候选：学品牌标志的做法——一个符号、一两种颜色、不写字。

用法：python tools_dev/logo_candidates5.py 输出文件夹
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontMetricsF, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap,
)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from logo_candidates3 import bg, canvas, font  # noqa: E402


def glyph_path(text: str, f: QFont, cx: float, cy: float) -> QPainterPath:
    fm = QFontMetricsF(f)
    path = QPainterPath()
    path.addText(cx - fm.horizontalAdvance(text) / 2, cy + (fm.ascent() - fm.descent()) / 2 - fm.descent() * 0.1, f, text)
    return path


# ---- Q：粗体 S 单字标，渐变填充，底下一条字幕线（像 Logitech 的 G）----
def logo_q(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#15161c", "#0b0c10")
    f = font(int(s * 0.62), "Arial Black", QFont.Weight.Black)
    path = glyph_path("S", f, s * 0.5, s * 0.46)
    g = QLinearGradient(s * 0.3, s * 0.15, s * 0.7, s * 0.8)
    g.setColorAt(0, QColor("#4fd1ff"))
    g.setColorAt(1, QColor("#7c4dff"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    # 字幕线：穿过 S 的「腰」，一段白
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(s * 0.28, s * 0.8, s * 0.44, s * 0.06), s * 0.03, s * 0.03)
    p.end()
    return pm


# ---- R：抖音式——白色字幕条符号，后面青色和品红的错位影子，黑底 ----
def logo_r(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#0f0f12", "#0f0f12")

    def bars(dx: float, dy: float, color: QColor) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawRoundedRect(QRectF(s * 0.2 + dx, s * 0.33 + dy, s * 0.6, s * 0.13), s * 0.065, s * 0.065)
        p.drawRoundedRect(QRectF(s * 0.2 + dx, s * 0.54 + dy, s * 0.38, s * 0.13), s * 0.065, s * 0.065)

    bars(-s * 0.03, -s * 0.03, QColor("#25f4ee"))
    bars(s * 0.03, s * 0.03, QColor("#fe2c55"))
    bars(0, 0, QColor("#ffffff"))
    p.end()
    return pm


# ---- S：实心渐变圆，镂空两条字幕 + 一个播放三角（像 Chrome 的圆）----
def logo_s(s: int) -> QPixmap:
    pm, p = canvas(s)
    circle = QRectF(s * 0.08, s * 0.08, s * 0.84, s * 0.84)
    g = QLinearGradient(circle.topLeft(), circle.bottomRight())
    g.setColorAt(0, QColor("#3b82f6"))
    g.setColorAt(1, QColor("#8b5cf6"))
    base = QPainterPath()
    base.addEllipse(circle)
    cut = QPainterPath()
    tri = QPainterPath()
    tri.moveTo(QPointF(s * 0.4, s * 0.26))
    tri.lineTo(QPointF(s * 0.66, s * 0.4))
    tri.lineTo(QPointF(s * 0.4, s * 0.54))
    tri.closeSubpath()
    cut.addPath(tri)
    cut.addRoundedRect(QRectF(s * 0.26, s * 0.62, s * 0.48, s * 0.07), s * 0.035, s * 0.035)
    cut.addRoundedRect(QRectF(s * 0.33, s * 0.74, s * 0.34, s * 0.07), s * 0.035, s * 0.035)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(base.subtracted(cut))
    p.end()
    return pm


# ---- T：只有一个符号——圆润的对话气泡剪影，里面一条字幕线（像 Discord 只有一个脸）----
def logo_t(s: int) -> QPixmap:
    pm, p = canvas(s)
    rect = QRectF(s * 0.1, s * 0.16, s * 0.8, s * 0.56)
    path = QPainterPath()
    path.addRoundedRect(rect, s * 0.2, s * 0.2)
    tail = QPainterPath()
    tail.moveTo(QPointF(s * 0.3, rect.bottom() - 2))
    tail.lineTo(QPointF(s * 0.2, s * 0.9))
    tail.lineTo(QPointF(s * 0.5, rect.bottom() - 2))
    tail.closeSubpath()
    path = path.united(tail)
    g = QLinearGradient(rect.topLeft(), rect.bottomRight())
    g.setColorAt(0, QColor("#5865f2"))
    g.setColorAt(1, QColor("#7c4dff"))
    line = QPainterPath()
    line.addRoundedRect(QRectF(s * 0.26, s * 0.4, s * 0.48, s * 0.085), s * 0.0425, s * 0.0425)
    line.addRoundedRect(QRectF(s * 0.26, s * 0.53, s * 0.28, s * 0.085), s * 0.0425, s * 0.0425)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path.subtracted(line))
    p.end()
    return pm


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    QGuiApplication(sys.argv)
    makers = [("Q", logo_q), ("R", logo_r), ("S", logo_s), ("T", logo_t)]
    big = 256
    sheet = QPixmap(len(makers) * (big + 40) + 40, big + 170)
    sheet.fill(QColor("#ffffff"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setPen(QColor("#1f2328"))
    p.setFont(font(20, "Microsoft YaHei UI", QFont.Weight.DemiBold))
    for i, (name, fn) in enumerate(makers):
        x = 40 + i * (big + 40)
        pm = fn(512)
        pm.save(str(out / f"logo_{name}.png"))
        p.drawPixmap(QRectF(x, 30, big, big), pm, QRectF(0, 0, 512, 512))
        p.drawPixmap(QRectF(x, 30 + big + 24, 32, 32), pm, QRectF(0, 0, 512, 512))
        p.drawPixmap(QRectF(x + 44, 30 + big + 16, 48, 48), pm, QRectF(0, 0, 512, 512))
        p.drawPixmap(QRectF(x + 104, 30 + big + 8, 64, 64), pm, QRectF(0, 0, 512, 512))
        p.drawText(QRectF(x, 30 + big + 84, big, 40), Qt.AlignmentFlag.AlignLeft, f"方案 {name}")
    p.end()
    sheet.save(str(out / "logo_candidates5.png"))
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
