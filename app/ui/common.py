"""各页面共用的小工具。"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QMessageBox, QWidget


def not_implemented(parent: QWidget | None, feature: str = "这个功能", stage: str = "") -> None:
    """未完成功能统一提示。"""
    text = f"{feature}还在开发中。"
    if stage:
        text += f"\n计划在{stage}完成。"
    QMessageBox.information(parent, "开发中", text)


def page_title(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-size: 22px; font-weight: 600; margin-bottom: 6px;")
    return label


def hint(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setStyleSheet("color: #666;")
    return label
