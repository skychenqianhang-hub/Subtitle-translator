"""顶栏图标：全部用代码画的单色线条图标，粗细、颜色、大小统一，不依赖字体或表情符号。"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

ICON_COLOR = ""         # 空 = 用当前主题的图标色
ICON_PX = 22            # 顶栏按钮里显示的大小


def _begin(size: int, color: str) -> tuple[QPixmap, QPainter]:
    if not color:
        from app.ui.theme import current_palette
        color = current_palette().get("icon", "#444444")
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), size / 14)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    return pm, painter


def globe_icon(size: int = 64, color: str = ICON_COLOR) -> QIcon:
    """地球：圆 + 赤道 + 两条纬线 + 一条经线椭圆。"""
    pm, painter = _begin(size, color)
    m = size * 0.1
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    painter.drawEllipse(r)
    painter.drawEllipse(QRectF(r.center().x() - r.width() * 0.22, r.top(), r.width() * 0.44, r.height()))
    painter.drawLine(QPointF(r.left(), r.center().y()), QPointF(r.right(), r.center().y()))
    for frac in (0.3, 0.7):
        y = r.top() + r.height() * frac
        half = (r.width() / 2) * (1 - (2 * frac - 1) ** 2) ** 0.5
        painter.drawLine(QPointF(r.center().x() - half, y), QPointF(r.center().x() + half, y))
    painter.end()
    return QIcon(pm)


def palette_icon(size: int = 64, color: str = ICON_COLOR) -> QIcon:
    """配色：左半填满的圆（明暗对比的通用符号），和地球、齿轮同一种线宽。"""
    pm, painter = _begin(size, color)
    m = size * 0.1
    r = QRectF(m, m, size - 2 * m, size - 2 * m)
    painter.drawEllipse(r)
    painter.setBrush(QColor(painter.pen().color()))
    painter.drawChord(r, 90 * 16, 180 * 16)
    painter.end()
    return QIcon(pm)


def gear_icon(size: int = 64, color: str = ICON_COLOR, teeth: int = 8) -> QIcon:
    """齿轮：8 个齿的轮廓 + 中间圆孔，和地球同样的线宽。"""
    pm, painter = _begin(size, color)
    c = QPointF(size / 2, size / 2)
    outer, inner, hole = size * 0.40, size * 0.30, size * 0.12
    path = QPainterPath()
    steps = teeth * 4                       # 每个齿：齿顶两点 + 齿谷两点
    for i in range(steps + 1):
        k = i % steps
        radius = outer if (k % 4) in (0, 1) else inner
        angle = 2 * math.pi * (i + (0.5 if (k % 4) in (1, 3) else 0) - 0.25) / steps
        pt = QPointF(c.x() + radius * math.cos(angle), c.y() + radius * math.sin(angle))
        if i == 0:
            path.moveTo(pt)
        else:
            path.lineTo(pt)
    path.closeSubpath()
    painter.drawPath(path)
    painter.drawEllipse(c, hole, hole)
    painter.end()
    return QIcon(pm)
