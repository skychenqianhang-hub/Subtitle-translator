"""第三轮 logo 候选：从名字 SubTranslator 本身取元素。

- Sub = 字幕：视频底部那一条白字黑边的字幕，和「CC」字幕标志这种人人认得的符号
- Translator = 翻译：双语上下两行（这个软件输出的就是「原文 + 译文」）、箭头
用法：python tools_dev/logo_candidates3.py 输出文件夹
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


def canvas(size: int) -> tuple[QPixmap, QPainter]:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    return pm, p


def bg(p: QPainter, s: int, c1: str, c2: str, radius: float = 0.225) -> None:
    g = QLinearGradient(0, 0, 0, s)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * radius, s * radius)


def font(px: int, family: str, weight: int = QFont.Weight.DemiBold, spacing: float = 0.0) -> QFont:
    f = QFont(family)
    f.setPixelSize(px)
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100 + spacing)
    return f


def outlined_text(p: QPainter, rect: QRectF, text: str, f: QFont, fill: str, outline: str, width: float) -> None:
    """白字黑边——真正的视频字幕写法。"""
    path = QPainterPath()
    fm = QFontMetricsF(f)
    # 用 QPainterPath 拿到文字轮廓，才能描边；位置按字体度量自己算，居中
    x = rect.center().x() - fm.horizontalAdvance(text) / 2
    y = rect.center().y() + (fm.ascent() - fm.descent()) / 2
    path.addText(x, y, f, text)
    pen = QPen(QColor(outline), width)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(QColor(fill))
    p.drawPath(path)


# ---- I：「CC」式字幕标志，改成「ST」（SubTranslator 首字母）----
def logo_i(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#2f6fed", "#1e4fc4")
    box = QRectF(s * 0.14, s * 0.26, s * 0.72, s * 0.48)
    pen = QPen(QColor("#ffffff"), s * 0.055)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawRoundedRect(box, s * 0.07, s * 0.07)
    p.setPen(QColor("#ffffff"))
    p.setFont(font(int(s * 0.3), "Segoe UI", QFont.Weight.Bold, spacing=4))
    p.drawText(box, Qt.AlignmentFlag.AlignCenter, "ST")
    p.end()
    return pm


# ---- J：真正的双语字幕——深色画面，上行 SUB、下行 字幕，白字黑边 ----
def logo_j(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#2a2f3a", "#111419")
    # 画面里一点光，像视频画面
    g = QLinearGradient(0, 0, s, s * 0.6)
    g.setColorAt(0, QColor(79, 107, 255, 90))
    g.setColorAt(1, QColor(124, 77, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.225, s * 0.225)
    # 真字幕的写法：白字 + 细黑边 + 一点投影（边太粗汉字会糊成一团）
    for dx, dy in ((s * 0.006, s * 0.008), (0, 0)):
        p.save()
        p.translate(dx, dy)
        shadowed = dx or dy
        outlined_text(p, QRectF(0, s * 0.28, s, s * 0.22), "SUB",
                      font(int(s * 0.21), "Segoe UI", QFont.Weight.Bold, spacing=8),
                      "#000000" if shadowed else "#ffffff", "#000000", s * 0.006)
        outlined_text(p, QRectF(0, s * 0.52, s, s * 0.24), "字幕",
                      font(int(s * 0.2), "Microsoft YaHei UI", QFont.Weight.DemiBold),
                      "#000000" if shadowed else "#ffffff", "#000000", s * 0.006)
        p.restore()
    p.end()
    return pm


# ---- K：双语字幕条，抽象版——上行蓝 Aa，下行渐变 文，一个小箭头连接 ----
def logo_k(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#ffffff", "#eef1f8")
    p.setPen(QColor("#1f2328"))
    p.setFont(font(int(s * 0.3), "Segoe UI", QFont.Weight.DemiBold))
    p.drawText(QRectF(0, s * 0.14, s, s * 0.34), Qt.AlignmentFlag.AlignCenter, "Sub")
    g = QLinearGradient(s * 0.2, 0, s * 0.8, 0)
    g.setColorAt(0, QColor("#2f6fed"))
    g.setColorAt(1, QColor("#7c4dff"))
    p.setPen(QPen(g, 1))
    # 渐变文字：先取轮廓再填渐变
    path = QPainterPath()
    f = font(int(s * 0.27), "Microsoft YaHei UI", QFont.Weight.Bold)
    fm = QFontMetricsF(f)
    path.addText(s / 2 - fm.horizontalAdvance("字幕") / 2, s * 0.67 + (fm.ascent() - fm.descent()) / 2, f, "字幕")
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawPath(path)
    # 中间细线（像字幕的分隔）
    p.setBrush(QColor("#2f6fed"))
    p.drawRoundedRect(QRectF(s * 0.4, s * 0.485, s * 0.2, s * 0.02), s * 0.01, s * 0.01)
    p.end()
    return pm


# ---- L：字幕条上的「S」，中间一笔变成箭头（Sub → Translate）----
def logo_l(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#2f6fed", "#7c4dff")
    # 深色字幕条
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(0, 0, 0, 110))
    p.drawRoundedRect(QRectF(s * 0.12, s * 0.58, s * 0.76, s * 0.2), s * 0.06, s * 0.06)
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(s * 0.2, s * 0.645, s * 0.36, s * 0.07), s * 0.035, s * 0.035)
    p.setBrush(QColor(255, 255, 255, 150))
    p.drawRoundedRect(QRectF(s * 0.6, s * 0.645, s * 0.2, s * 0.07), s * 0.035, s * 0.035)
    # 大写 S，中段换成箭头
    p.setPen(QColor("#ffffff"))
    p.setFont(font(int(s * 0.46), "Segoe UI", QFont.Weight.Bold))
    p.drawText(QRectF(0, s * 0.04, s, s * 0.54), Qt.AlignmentFlag.AlignCenter, "S")
    pen = QPen(QColor("#7c4dff"), s * 0.04)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.36, s * 0.31), QPointF(s * 0.64, s * 0.31))
    p.drawLine(QPointF(s * 0.57, s * 0.25), QPointF(s * 0.64, s * 0.31))
    p.drawLine(QPointF(s * 0.57, s * 0.37), QPointF(s * 0.64, s * 0.31))
    p.end()
    return pm


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    QGuiApplication(sys.argv)
    makers = [("I", logo_i), ("J", logo_j), ("K", logo_k), ("L", logo_l)]
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
    sheet.save(str(out / "logo_candidates3.png"))
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
