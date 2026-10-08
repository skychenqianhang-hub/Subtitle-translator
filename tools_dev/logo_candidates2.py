"""第二轮 logo 候选：渐变底、柔和阴影、更少的元素（用户觉得第一轮纯色方块「廉价」）。

用法：python tools_dev/logo_candidates2.py 输出文件夹
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QGuiApplication, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)


def canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return pm, p


def gradient_bg(p: QPainter, s: int, c1: str, c2: str, radius: float = 0.225) -> None:
    g = QLinearGradient(0, 0, s, s)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * radius, s * radius)
    # 左上角一点柔光，底色有层次
    glow = QRadialGradient(QPointF(s * 0.25, s * 0.15), s * 0.8)
    glow.setColorAt(0, QColor(255, 255, 255, 60))
    glow.setColorAt(1, QColor(255, 255, 255, 0))
    p.setBrush(glow)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * radius, s * radius)


def shadow(p: QPainter, path: QPainterPath, s: int, alpha: int = 70) -> None:
    """用几层半透明偏移模拟柔和投影。"""
    for i in range(6, 0, -1):
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 40, int(alpha / 6)))
        p.save()
        p.translate(0, s * 0.012 * i)
        p.drawPath(path)
        p.restore()


def bubble_path(rect: QRectF) -> QPainterPath:
    r = rect.height() * 0.28
    path = QPainterPath()
    path.addRoundedRect(rect, r, r)
    tail = QPainterPath()
    tail.moveTo(rect.left() + rect.width() * 0.22, rect.bottom() - 1)
    tail.lineTo(rect.left() + rect.width() * 0.14, rect.bottom() + rect.height() * 0.2)
    tail.lineTo(rect.left() + rect.width() * 0.42, rect.bottom() - 1)
    tail.closeSubpath()
    return path.united(tail)


def font(px: int, family: str = "Segoe UI", weight: int = QFont.Weight.DemiBold) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


# ---- E：渐变底，白色气泡，气泡里两条字幕（镂空）----
def logo_e(s: int) -> QPixmap:
    pm, p = canvas(s)
    gradient_bg(p, s, "#4f6bff", "#7c4dff")
    rect = QRectF(s * 0.18, s * 0.2, s * 0.64, s * 0.46)
    path = bubble_path(rect)
    shadow(p, path, s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawPath(path)
    # 镂空的两条字幕线
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
    p.drawRoundedRect(QRectF(s * 0.28, s * 0.33, s * 0.44, s * 0.065), s * 0.032, s * 0.032)
    p.drawRoundedRect(QRectF(s * 0.28, s * 0.45, s * 0.3, s * 0.065), s * 0.032, s * 0.032)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
    # 把镂空处补回渐变底色（Clear 会把底也清掉）
    p.save()
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(s * 0.28, s * 0.33, s * 0.44, s * 0.065), s * 0.032, s * 0.032)
    clip.addRoundedRect(QRectF(s * 0.28, s * 0.45, s * 0.3, s * 0.065), s * 0.032, s * 0.032)
    p.setClipPath(clip)
    gradient_bg(p, s, "#4f6bff", "#7c4dff")
    p.restore()
    p.end()
    return pm


# ---- F：渐变底，白色气泡里「A 文」细体，字幕线在气泡下方 ----
def logo_f(s: int) -> QPixmap:
    pm, p = canvas(s)
    gradient_bg(p, s, "#2b6cf6", "#1b3fb8")
    rect = QRectF(s * 0.16, s * 0.17, s * 0.68, s * 0.42)
    path = bubble_path(rect)
    shadow(p, path, s)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("#ffffff"))
    p.drawPath(path)
    p.setPen(QColor("#2b5fd8"))
    p.setFont(font(int(s * 0.24), "Segoe UI", QFont.Weight.Medium))
    p.drawText(QRectF(rect.left(), rect.top(), rect.width() * 0.5, rect.height()), Qt.AlignmentFlag.AlignCenter, "A")
    p.setFont(font(int(s * 0.2), "Microsoft YaHei UI", QFont.Weight.Normal))
    p.drawText(QRectF(rect.left() + rect.width() * 0.5, rect.top(), rect.width() * 0.5, rect.height()),
               Qt.AlignmentFlag.AlignCenter, "文")
    # 中间细分隔线
    p.setPen(QPen(QColor("#2b5fd8"), s * 0.008))
    p.drawLine(QPointF(rect.center().x(), rect.top() + rect.height() * 0.28),
               QPointF(rect.center().x(), rect.bottom() - rect.height() * 0.28))
    # 字幕线
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 230))
    p.drawRoundedRect(QRectF(s * 0.22, s * 0.72, s * 0.56, s * 0.06), s * 0.03, s * 0.03)
    p.setBrush(QColor(255, 255, 255, 120))
    p.drawRoundedRect(QRectF(s * 0.32, s * 0.82, s * 0.36, s * 0.06), s * 0.03, s * 0.03)
    p.end()
    return pm


# ---- G：深色底，渐变发光的字幕条 + 一个小「文」 ----
def logo_g(s: int) -> QPixmap:
    pm, p = canvas(s)
    gradient_bg(p, s, "#1b2030", "#0f1320")
    # 发光的字幕条（先画几层模糊的半透明，再画实体）
    bars = [QRectF(s * 0.18, s * 0.56, s * 0.64, s * 0.09), QRectF(s * 0.3, s * 0.71, s * 0.4, s * 0.09)]
    g = QLinearGradient(s * 0.18, 0, s * 0.82, 0)
    g.setColorAt(0, QColor("#5b8cff"))
    g.setColorAt(1, QColor("#9b6bff"))
    for r in bars:
        for i in range(5, 0, -1):
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(110, 120, 255, 18))
            grow = s * 0.012 * i
            p.drawRoundedRect(r.adjusted(-grow, -grow, grow, grow), r.height(), r.height())
        p.setBrush(g)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
    # 上方「文」用渐变描边感的白字
    p.setPen(QColor("#ffffff"))
    p.setFont(font(int(s * 0.34), "Microsoft YaHei UI", QFont.Weight.Light))
    p.drawText(QRectF(0, s * 0.1, s, s * 0.42), Qt.AlignmentFlag.AlignCenter, "文")
    p.end()
    return pm


# ---- H：浅色底，渐变圆形徽章，白色气泡镂空字幕 ----
def logo_h(s: int) -> QPixmap:
    pm, p = canvas(s)
    gradient_bg(p, s, "#f7f8fc", "#e9ecf5")
    circle = QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72)
    path = QPainterPath()
    path.addEllipse(circle)
    shadow(p, path, s, alpha=50)
    g = QLinearGradient(circle.topLeft(), circle.bottomRight())
    g.setColorAt(0, QColor("#4f6bff"))
    g.setColorAt(1, QColor("#7c4dff"))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawEllipse(circle)
    bubble = bubble_path(QRectF(s * 0.3, s * 0.32, s * 0.4, s * 0.28))
    p.setBrush(QColor("#ffffff"))
    p.drawPath(bubble)
    p.setBrush(QColor("#5c6cff"))
    p.drawRoundedRect(QRectF(s * 0.36, s * 0.39, s * 0.28, s * 0.04), s * 0.02, s * 0.02)
    p.drawRoundedRect(QRectF(s * 0.36, s * 0.47, s * 0.18, s * 0.04), s * 0.02, s * 0.02)
    p.end()
    return pm


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    QGuiApplication(sys.argv)
    makers = [("E", logo_e), ("F", logo_f), ("G", logo_g), ("H", logo_h)]
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
    sheet.save(str(out / "logo_candidates2.png"))
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
