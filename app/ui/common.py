"""各页面共用的小工具。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtWidgets import QLabel, QMessageBox, QWidget


def not_implemented(parent: QWidget | None, feature: str | None = None, stage: str = "") -> None:
    """未完成功能统一提示。"""
    text = tr("{0}还在开发中。", feature or tr("这个功能"))
    if stage:
        text += tr("\n计划在{0}完成。", stage)
    QMessageBox.information(parent, tr("开发中"), text)


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 22px; font-weight: 600; margin-bottom: 6px;")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #666;")
    return label
