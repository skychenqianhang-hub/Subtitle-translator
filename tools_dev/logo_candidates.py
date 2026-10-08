"""画几款 logo 候选（纯代码绘制，256px），拼成一张对比图给用户挑。

用法：python tools_dev/logo_candidates.py 输出文件夹
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPainterPath, QPen, QPixmap

BLUE = QColor("#2f6fed")
DEEP = QColor("#1f4fc2")
WHITE = QColor("#ffffff")


def canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    return pm, p


def rounded_bg(p: QPainter, size: int, color: QColor, radius_ratio: float = 0.22) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(color)
    p.drawRoundedRect(QRectF(0, 0, size, size), size * radius_ratio, size * radius_ratio)


def cjk_font(px: int, bold: bool = True) -> QFont:
    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(px)
    f.setBold(bold)
    return f


# ---- A：屏幕 + 两条字幕 + 文/A ----
def logo_a(size: int) -> QPixmap:
    pm, p = canvas(size)
    rounded_bg(p, size, BLUE)
    s = size
    # 屏幕（白色描边圆角矩形）
    pen = QPen(WHITE, s * 0.06)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.2, s * 0.68, s * 0.5), s * 0.06, s * 0.06)
    # 两条字幕
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(s * 0.26, s * 0.5, s * 0.48, s * 0.055), s * 0.027, s * 0.027)
    p.drawRoundedRect(QRectF(s * 0.34, s * 0.59, s * 0.32, s * 0.055), s * 0.027, s * 0.027)
    # 屏幕上方「文 A」
    p.setPen(WHITE)
    p.setFont(cjk_font(int(s * 0.2)))
    p.drawText(QRectF(s * 0.2, s * 0.22, s * 0.3, s * 0.24), Qt.AlignmentFlag.AlignCenter, "文")
    p.drawText(QRectF(s * 0.5, s * 0.22, s * 0.3, s * 0.24), Qt.AlignmentFlag.AlignCenter, "A")
    # 底部一行小字幕暗示
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawRoundedRect(QRectF(s * 0.3, s * 0.78, s * 0.4, s * 0.045), s * 0.02, s * 0.02)
    p.end()
    return pm


# ---- B：两个对话气泡，一个「文」一个「A」 ----
def logo_b(size: int) -> QPixmap:
    pm, p = canvas(size)
    rounded_bg(p, size, BLUE)
    s = size

    def bubble(rect: QRectF, tail_left: bool, fill: QColor, text: str, text_color: QColor) -> None:
        path = QPainterPath()
        path.addRoundedRect(rect, rect.height() * 0.3, rect.height() * 0.3)
        tail = QPainterPath()
        if tail_left:
            tail.moveTo(rect.left() + rect.width() * 0.18, rect.bottom() - 2)
            tail.lineTo(rect.left() + rect.width() * 0.08, rect.bottom() + rect.height() * 0.22)
            tail.lineTo(rect.left() + rect.width() * 0.38, rect.bottom() - 2)
        else:
            tail.moveTo(rect.right() - rect.width() * 0.18, rect.top() + 2)
            tail.lineTo(rect.right() - rect.width() * 0.08, rect.top() - rect.height() * 0.22)
            tail.lineTo(rect.right() - rect.width() * 0.38, rect.top() + 2)
        path = path.united(tail)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(fill)
        p.drawPath(path)
        p.setPen(text_color)
        p.setFont(cjk_font(int(rect.height() * 0.62)))
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, text)

    bubble(QRectF(s * 0.12, s * 0.16, s * 0.46, s * 0.34), True, WHITE, "文", BLUE)
    bubble(QRectF(s * 0.42, s * 0.5, s * 0.46, s * 0.34), False, DEEP, "A", WHITE)
    p.end()
    return pm


# ---- C：字幕条 + 箭头，极简 ----
def logo_c(size: int) -> QPixmap:
    pm, p = canvas(size)
    rounded_bg(p, size, BLUE)
    s = size
    p.setPen(WHITE)
    p.setFont(cjk_font(int(s * 0.30)))
    p.drawText(QRectF(s * 0.08, s * 0.14, s * 0.4, s * 0.36), Qt.AlignmentFlag.AlignCenter, "A")
    p.drawText(QRectF(s * 0.52, s * 0.14, s * 0.4, s * 0.36), Qt.AlignmentFlag.AlignCenter, "文")
    # 中间小箭头
    pen = QPen(WHITE, s * 0.035)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.44, s * 0.32), QPointF(s * 0.56, s * 0.32))
    p.drawLine(QPointF(s * 0.52, s * 0.28), QPointF(s * 0.56, s * 0.32))
    p.drawLine(QPointF(s * 0.52, s * 0.36), QPointF(s * 0.56, s * 0.32))
    # 下方两条字幕
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(WHITE)
    p.drawRoundedRect(QRectF(s * 0.2, s * 0.6, s * 0.6, s * 0.075), s * 0.037, s * 0.037)
    p.setBrush(QColor(255, 255, 255, 170))
    p.drawRoundedRect(QRectF(s * 0.3, s * 0.73, s * 0.4, s * 0.075), s * 0.037, s * 0.037)
    p.end()
    return pm


# ---- D：圆形「文」+ 字幕条，白底蓝字 ----
def logo_d(size: int) -> QPixmap:
    pm, p = canvas(size)
    rounded_bg(p, size, WHITE)
    s = size
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BLUE)
    p.drawEllipse(QRectF(s * 0.22, s * 0.1, s * 0.56, s * 0.56))
    p.setPen(WHITE)
    p.setFont(cjk_font(int(s * 0.32)))
    p.drawText(QRectF(s * 0.22, s * 0.1, s * 0.56, s * 0.56), Qt.AlignmentFlag.AlignCenter, "文")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(BLUE)
    p.drawRoundedRect(QRectF(s * 0.18, s * 0.73, s * 0.64, s * 0.07), s * 0.035, s * 0.035)
    p.setBrush(QColor(BLUE.red(), BLUE.green(), BLUE.blue(), 140))
    p.drawRoundedRect(QRectF(s * 0.3, s * 0.84, s * 0.4, s * 0.07), s * 0.035, s * 0.035)
    p.end()
    return pm


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    QGuiApplication(sys.argv)
    makers = [("A", logo_a), ("B", logo_b), ("C", logo_c), ("D", logo_d)]
    big = 256
    small = 32
    sheet = QPixmap(len(makers) * (big + 40) + 40, big + 160)
    sheet.fill(QColor("#f3f4f6"))
    p = QPainter(sheet)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QColor("#1f2328"))
    p.setFont(cjk_font(20, bold=True))
    for i, (name, fn) in enumerate(makers):
        x = 40 + i * (big + 40)
        pm = fn(big)
        pm.save(str(out / f"logo_{name}.png"))
        p.drawPixmap(x, 30, pm)
        # 小尺寸预览（任务栏 / 标题栏那么大）
        p.drawPixmap(x, 30 + big + 24, fn(small))
        p.drawPixmap(x + 44, 30 + big + 16, fn(48))
        p.drawText(QRectF(x, 30 + big + 76, big, 40), Qt.AlignmentFlag.AlignLeft, f"方案 {name}")
    p.end()
    sheet.save(str(out / "logo_candidates.png"))
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
