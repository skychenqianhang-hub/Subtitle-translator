"""内容场景选择器：板块 + 子板块 两个下拉框，以及「管理场景」按钮。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from app.core.profiles.defaults import scene_display_name, scene_tree


class ScenePicker(QWidget):
    manage_requested = Signal()
    changed = Signal(str)  # 例如 "游戏 → Valorant"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree = scene_tree()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("板块"))
        self.section = QComboBox()
        self.section.addItems(list(self._tree.keys()))
        self.section.setMinimumWidth(120)
        layout.addWidget(self.section)
        layout.addWidget(QLabel("子板块"))
        self.sub = QComboBox()
        self.sub.setMinimumWidth(140)
        layout.addWidget(self.sub)
        self.manage = QPushButton("管理场景…")
        self.manage.clicked.connect(self.manage_requested.emit)
        layout.addWidget(self.manage)
        layout.addStretch(1)

        self.section.currentTextChanged.connect(self._refresh_sub)
        self.sub.currentTextChanged.connect(lambda _: self.changed.emit(self.current_name()))
        self._refresh_sub(self.section.currentText())

    def _refresh_sub(self, section: str) -> None:
        subs = self._tree.get(section, [])
        self.sub.blockSignals(True)
        self.sub.clear()
        self.sub.addItem("（不选）", "")
        for s in subs:
            self.sub.addItem(s, s)
        self.sub.setEnabled(bool(subs))
        self.sub.blockSignals(False)
        self.changed.emit(self.current_name())

    def current_name(self) -> str:
        return scene_display_name(self.section.currentText(), self.sub.currentData() or "")

    def set_current(self, name: str) -> None:
        """按 "板块 → 子板块" 或 "板块" 还原选择。"""
        section, _, sub = name.partition(" → ")
        idx = self.section.findText(section.strip())
        if idx < 0:
            return
        self.section.setCurrentIndex(idx)
        idx = self.sub.findData(sub.strip())
        self.sub.setCurrentIndex(max(0, idx))
