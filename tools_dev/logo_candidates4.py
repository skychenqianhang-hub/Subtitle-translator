"""第四轮 logo 候选：不用任何中文元素。

用法：python tools_dev/logo_candidates4.py 输出文件夹
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
from logo_candidates3 import bg, canvas, font, logo_i, outlined_text  # noqa: E402


# ---- M：真·字幕，上行 SUB、下行 TRANSLATOR ----
def logo_m(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#2a2f3a", "#111419")
    g = QLinearGradient(0, 0, s, s * 0.6)
    g.setColorAt(0, QColor(79, 107, 255, 90))
    g.setColorAt(1, QColor(124, 77, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.225, s * 0.225)
    for dx, dy in ((s * 0.006, s * 0.008), (0, 0)):
        p.save()
        p.translate(dx, dy)
        sh = dx or dy
        outlined_text(p, QRectF(0, s * 0.3, s, s * 0.24), "SUB",
                      font(int(s * 0.26), "Segoe UI", QFont.Weight.Bold, spacing=8),
                      "#000000" if sh else "#ffffff", "#000000", s * 0.006)
        outlined_text(p, QRectF(0, s * 0.56, s, s * 0.14), "TRANSLATOR",
                      font(int(s * 0.095), "Segoe UI", QFont.Weight.DemiBold, spacing=18),
                      "#000000" if sh else "#ffffff", "#000000", s * 0.005)
        p.restore()
    p.end()
    return pm


# ---- O：字幕上的 A → B ----
def logo_o(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#2a2f3a", "#111419")
    g = QLinearGradient(0, s, s, 0)
    g.setColorAt(0, QColor(79, 107, 255, 110))
    g.setColorAt(1, QColor(124, 77, 255, 0))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(QRectF(0, 0, s, s), s * 0.225, s * 0.225)
    f = font(int(s * 0.3), "Segoe UI", QFont.Weight.Bold)
    for dx, dy in ((s * 0.006, s * 0.008), (0, 0)):
        p.save()
        p.translate(dx, dy)
        sh = dx or dy
        outlined_text(p, QRectF(s * 0.08, s * 0.3, s * 0.34, s * 0.3), "A", f, "#000000" if sh else "#ffffff", "#000000", s * 0.006)
        outlined_text(p, QRectF(s * 0.58, s * 0.3, s * 0.34, s * 0.3), "B", f, "#000000" if sh else "#ffffff", "#000000", s * 0.006)
        p.restore()
    pen = QPen(QColor("#8b9cff"), s * 0.035)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    y = s * 0.45
    p.drawLine(QPointF(s * 0.43, y), QPointF(s * 0.57, y))
    p.drawLine(QPointF(s * 0.52, y - s * 0.045), QPointF(s * 0.57, y))
    p.drawLine(QPointF(s * 0.52, y + s * 0.045), QPointF(s * 0.57, y))
    # 下方一条淡字幕线
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 120))
    p.drawRoundedRect(QRectF(s * 0.28, s * 0.68, s * 0.44, s * 0.05), s * 0.025, s * 0.025)
    p.end()
    return pm


# ---- P：抽象——白色字幕条变成渐变字幕条 ----
def logo_p(s: int) -> QPixmap:
    pm, p = canvas(s)
    bg(p, s, "#1b2030", "#0f1320")
    p.setPen(Qt.PenStyle.NoPen)
    # 上：原文（白，两段）
    p.setBrush(QColor("#ffffff"))
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.3, s * 0.42, s * 0.09), s * 0.045, s * 0.045)
    p.drawRoundedRect(QRectF(s * 0.63, s * 0.3, s * 0.21, s * 0.09), s * 0.045, s * 0.045)
    # 下：译文（渐变，两段，位置错开一点，像翻译后长度变了）
    g = QLinearGradient(s * 0.16, 0, s * 0.84, 0)
    g.setColorAt(0, QColor("#5b8cff"))
    g.setColorAt(1, QColor("#9b6bff"))
    p.setBrush(g)
    p.drawRoundedRect(QRectF(s * 0.16, s * 0.58, s * 0.28, s * 0.09), s * 0.045, s * 0.045)
    p.drawRoundedRect(QRectF(s * 0.49, s * 0.58, s * 0.35, s * 0.09), s * 0.045, s * 0.045)
    # 中间向下的小箭头
    pen = QPen(QColor(255, 255, 255, 170), s * 0.03)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.drawLine(QPointF(s * 0.5, s * 0.43), QPointF(s * 0.5, s * 0.53))
    p.drawLine(QPointF(s * 0.46, s * 0.49), QPointF(s * 0.5, s * 0.53))
    p.drawLine(QPointF(s * 0.54, s * 0.49), QPointF(s * 0.5, s * 0.53))
    p.end()
    return pm


def main() -> int:
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)
    QGuiApplication(sys.argv)
    makers = [("M", logo_m), ("N", logo_i), ("O", logo_o), ("P", logo_p)]
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
    sheet.save(str(out / "logo_candidates4.png"))
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
