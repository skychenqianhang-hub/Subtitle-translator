"""各页面共用的小工具。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QLabel, QMessageBox, QToolButton, QVBoxLayout, QWidget


def not_implemented(parent: QWidget | None, feature: str | None = None, stage: str = "") -> None:
    """未完成功能统一提示。"""
    text = tr("{0}还在开发中。", feature or tr("这个功能"))
    if stage:
        text += tr("\n计划在{0}完成。", stage)
    QMessageBox.information(parent, tr("开发中"), text)


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("pageTitle")          # 样式在 theme.py 里按 objectName 定
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setObjectName("hint")
    return label


def set_status(label: QLabel, kind: str) -> None:
    """状态文字的颜色角色：ok / error / info / plain。改 objectName 后要让样式表重新套一遍。"""
    name = {"ok": "statusOk", "error": "statusError", "info": "statusInfo"}.get(kind, "")
    if label.objectName() != name:
        label.setObjectName(name)
        label.style().unpolish(label)
        label.style().polish(label)


def card() -> tuple[QFrame, QVBoxLayout]:
    """圆角卡片（样式在 theme.py 的 QFrame#card）。返回卡片和它的竖向布局。"""
    frame = QFrame()
    frame.setObjectName("card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(16, 14, 16, 14)
    layout.setSpacing(10)
    return frame, layout


class Collapsible(QWidget):
    """「▸ 高级」这种可折叠区：一个带箭头的按钮 + 默认收起的内容。"""

    def __init__(self, title: str, content: QWidget, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.content = content
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.toggle = QToolButton()
        self.toggle.setObjectName("advancedToggle")
        self.toggle.setText(title)
        self.toggle.setCheckable(True)
        self.toggle.setArrowType(Qt.ArrowType.RightArrow)
        self.toggle.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.toggle.toggled.connect(self._on_toggle)
        layout.addWidget(self.toggle)
        layout.addWidget(content)
        content.setVisible(False)

    def _on_toggle(self, on: bool) -> None:
        self.content.setVisible(on)
        self.toggle.setArrowType(Qt.ArrowType.DownArrow if on else Qt.ArrowType.RightArrow)

    def set_open(self, on: bool) -> None:
        self.toggle.setChecked(on)
