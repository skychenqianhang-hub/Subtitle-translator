"""内容场景选择器：板块 + 子板块 两个下拉框，以及「管理场景」按钮。

板块 = 「通用」以及它的直接子场景（游戏、电影……）；
子板块 = 所选板块下面的所有后代（多层的用「→」连起来显示）。
保存和发出的都是场景的唯一名字（例如 "Valorant"），显示用路径（"游戏 → Valorant"）。
"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QWidget

from app.core.profiles.store import AUTO_LABEL, AUTO_SCENE, ROOT_NAME, ProfileStore

_NONE = ""


class ScenePicker(QWidget):
    manage_requested = Signal()
    changed = Signal(str)  # 场景名，例如 "Valorant" 或 "通用"

    def __init__(self, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._loading = False
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel(tr("板块")))
        self.section = QComboBox()
        self.section.setMinimumWidth(120)
        layout.addWidget(self.section)
        layout.addWidget(QLabel(tr("子板块")))
        self.sub = QComboBox()
        self.sub.setMinimumWidth(160)
        layout.addWidget(self.sub)
        self.manage = QPushButton(tr("管理场景…"))
        self.manage.clicked.connect(self.manage_requested.emit)
        layout.addWidget(self.manage)
        layout.addStretch(1)

        self.section.currentIndexChanged.connect(self._on_section)
        self.sub.currentIndexChanged.connect(self._emit)
        self.reload()

    # ------------------------------------------------------------ 数据
    def reload(self, keep: str | None = None) -> None:
        """场景列表变化后重新填充；keep = 想保持选中的场景名。"""
        current = keep if keep is not None else self.current_name()
        self._loading = True
        self.section.clear()
        self.section.addItem(tr(AUTO_LABEL), AUTO_SCENE)
        self.section.addItem(tr(ROOT_NAME), ROOT_NAME)
        for p in self.store.children(ROOT_NAME):
            self.section.addItem(tr(p.name), p.name)
        self._loading = False
        self.set_current(current or ROOT_NAME)

    def _fill_sub(self, section: str) -> None:
        self._loading = True
        self.sub.clear()
        self.sub.addItem(tr("（不选）"), _NONE)
        if section not in (ROOT_NAME, AUTO_SCENE):
            for d in self.store.descendants(section):
                path = self.store.path(d.name)
                # 去掉「通用 → 板块」前缀，只显示板块下面的层级
                label = " → ".join(tr(x) for x in path[2:]) if len(path) > 2 else tr(d.name)
                self.sub.addItem(label, d.name)
        self.sub.setEnabled(self.sub.count() > 1)
        self._loading = False

    def _on_section(self) -> None:
        if self._loading:
            return
        self._fill_sub(self.section.currentData() or ROOT_NAME)
        self._emit()

    def _emit(self) -> None:
        if not self._loading:
            self.changed.emit(self.current_name())

    # ------------------------------------------------------------ 取值
    def current_name(self) -> str:
        sub = self.sub.currentData() if self.sub.count() else _NONE
        if sub:
            return sub
        return self.section.currentData() or ROOT_NAME

    def current_display(self) -> str:
        return self.store.display_name(self.current_name())

    def is_auto(self) -> bool:
        return self.section.currentData() == AUTO_SCENE

    def set_current(self, name: str) -> None:
        if name == AUTO_SCENE:
            self._loading = True
            self.section.setCurrentIndex(max(0, self.section.findData(AUTO_SCENE)))
            self._loading = False
            self._fill_sub(AUTO_SCENE)
            self.changed.emit(AUTO_SCENE)
            return
        if name not in self.store.profiles:
            name = ROOT_NAME
        path = self.store.path(name)          # ["通用", 板块, ..., name]
        section = path[1] if len(path) > 1 else ROOT_NAME
        self._loading = True
        idx = self.section.findData(section)
        self.section.setCurrentIndex(max(0, idx))
        self._loading = False
        self._fill_sub(section)
        self._loading = True
        idx = self.sub.findData(name) if len(path) > 2 else 0
        self.sub.setCurrentIndex(max(0, idx))
        self._loading = False
        self.changed.emit(self.current_name())
