"""内容场景选择器：逐级下拉。

第一个下拉框列出顶层（自动 / 通用 / 游戏 / 电影……）；选中一个有子场景的项，右边自动多出一个下拉框列它的子场景；
再选中还有子场景的，再多出一个……有几层就出几个，用户不用看一整串「游戏 → Valorant → 某主播」。
保存和发出的都是场景的唯一名字（例如 "Valorant"），显示用路径。
"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QPushButton, QWidget

from app.core.profiles.store import AUTO_LABEL, AUTO_SCENE, ROOT_NAME, ProfileStore

_NONE = ""   # 子级下拉框里「（不选）」的值：停在父级


class ScenePicker(QWidget):
    manage_requested = Signal()
    changed = Signal(str)  # 场景名，例如 "Valorant"、"通用" 或 AUTO_SCENE

    def __init__(self, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._loading = False
        self.combos: list[QComboBox] = []
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.combo = self._new_combo()                # 第一级；下面几级按需添加
        self.combo.setToolTip(tr("场景决定术语表、纠错规则和识别提示词。「自动」会按识别到的内容自己挑。"))
        self.manage = QPushButton(tr("管理场景…"))
        self.manage.clicked.connect(self.manage_requested.emit)
        self._layout.addWidget(self.manage)
        self.reload()

    # ------------------------------------------------------------ 结构
    def _new_combo(self) -> QComboBox:
        c = QComboBox()
        c.setMinimumWidth(130)
        level = len(self.combos)
        c.currentIndexChanged.connect(lambda _i, lv=level: self._on_level_changed(lv))
        self._layout.insertWidget(level, c)
        self.combos.append(c)
        return c

    def _drop_levels_after(self, level: int) -> None:
        while len(self.combos) > level + 1:
            c = self.combos.pop()
            self._layout.removeWidget(c)
            c.deleteLater()

    def _fill_children(self, level: int, parent: str) -> None:
        """第 level 级下拉框列 parent 的子场景（有子场景才出现）。"""
        self._drop_levels_after(level - 1)
        children = self.store.children(parent)
        if not children:
            return
        c = self._new_combo()
        self._loading = True
        c.addItem(tr("（不选）"), _NONE)
        for p in children:
            c.addItem(tr(p.name), p.name)
        self._loading = False

    def _on_level_changed(self, level: int) -> None:
        if self._loading or level >= len(self.combos):
            return
        value = self.combos[level].currentData()
        if value in (_NONE, AUTO_SCENE, None) or (level == 0 and value == ROOT_NAME):
            self._drop_levels_after(level)      # 「通用」的子场景已经列在第一级里了，不再往下出
        else:
            self._fill_children(level + 1, value)
        self.changed.emit(self.current_name())

    # ------------------------------------------------------------ 数据
    def reload(self, keep: str | None = None) -> None:
        """场景列表变化后重新填充；keep = 想保持选中的场景名。"""
        current = keep if keep is not None else self.current_name()
        self._loading = True
        self._drop_levels_after(0)
        self.combo.clear()
        self.combo.addItem(tr(ROOT_NAME), ROOT_NAME)
        for p in self.store.children(ROOT_NAME):
            self.combo.addItem(tr(p.name), p.name)
        self.combo.addItem(tr(AUTO_LABEL), AUTO_SCENE)
        self._loading = False
        self.set_current(current or ROOT_NAME)

    # ------------------------------------------------------------ 取值
    def current_name(self) -> str:
        name = ROOT_NAME
        for c in self.combos:
            v = c.currentData()
            if v in (_NONE, None):
                break
            name = v
        return name

    def current_display(self) -> str:
        return self.store.display_name(self.current_name())

    def is_auto(self) -> bool:
        return self.combo.currentData() == AUTO_SCENE

    def set_current(self, name: str) -> None:
        if name != AUTO_SCENE and name not in self.store.profiles:
            name = ROOT_NAME
        # 路径 ["通用", "游戏", "Valorant"] → 第一级选「游戏」，第二级选「Valorant」，再出第三级（若有）
        path = [AUTO_SCENE] if name == AUTO_SCENE else self.store.path(name)[1:]
        self._loading = True
        self._drop_levels_after(0)
        self.combo.setCurrentIndex(max(0, self.combo.findData(path[0] if path else ROOT_NAME)))
        self._loading = False
        for level, node in enumerate(path):
            if node == AUTO_SCENE:
                break
            self._fill_children(level + 1, node)
            if level + 1 < len(path) and level + 1 < len(self.combos):
                self._loading = True
                self.combos[level + 1].setCurrentIndex(max(0, self.combos[level + 1].findData(path[level + 1])))
                self._loading = False
        self.changed.emit(self.current_name())
