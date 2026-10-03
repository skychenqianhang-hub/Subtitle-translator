"""场景管理页：左侧场景树，右侧编辑该场景自己的设置（继承来的另外显示）。"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.config import ASR_MODELS, TRANSLATE_MODELS, TRANSLATE_PROVIDERS
from app.core.errors import UserFacingError, friendly_message
from app.core.profiles.glossary_io import export_csv, import_pairs
from app.core.profiles.store import ROOT_NAME, Profile, ProfileStore
from app.ui.common import hint, page_title

_INHERIT = ""   # 下拉框里「继承父场景」的 data


class PairTable(QTableWidget):
    """两列表格：原文 / 译文 或 听错 / 正确。"""

    def __init__(self, headers: tuple[str, str], parent: QWidget | None = None) -> None:
        super().__init__(0, 2, parent)
        self.setHorizontalHeaderLabels(list(headers))
        self.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

    def set_pairs(self, pairs: dict[str, str]) -> None:
        self.setRowCount(0)
        for k, v in pairs.items():
            self.add_row(k, v)

    def add_row(self, k: str = "", v: str = "") -> None:
        r = self.rowCount()
        self.insertRow(r)
        self.setItem(r, 0, QTableWidgetItem(k))
        self.setItem(r, 1, QTableWidgetItem(v))
        if not k:
            self.setCurrentCell(r, 0)
            self.editItem(self.item(r, 0))

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.selectedIndexes()}, reverse=True)
        for r in rows:
            self.removeRow(r)

    def pairs(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for r in range(self.rowCount()):
            k = (self.item(r, 0).text() if self.item(r, 0) else "").strip()
            v = (self.item(r, 1).text() if self.item(r, 1) else "").strip()
            if k:
                out[k] = v
        return out


class ProfilesPage(QWidget):
    profiles_changed = Signal()   # 场景树或内容有变化（给主页的选择器刷新用）

    def __init__(self, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._current: str | None = None
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.addWidget(page_title("场景管理"))
        layout.addWidget(hint("场景是树状的：子场景自动继承父场景的全部设置。术语表、纠错规则、专有名词提示是「合并」继承，"
                              "子场景只需要填自己多出来的部分；同一个词子场景的写法优先。"))

        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        # ---------------- 左：场景树 ----------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("场景")
        self.tree.currentItemChanged.connect(self._on_tree_select)
        left_layout.addWidget(self.tree, 1)
        btn_row = QHBoxLayout()
        self.add_button = QPushButton("新建子场景")
        self.add_button.clicked.connect(self._add_child)
        self.rename_button = QPushButton("重命名")
        self.rename_button.clicked.connect(self._rename)
        self.delete_button = QPushButton("删除")
        self.delete_button.clicked.connect(self._delete)
        for b in (self.add_button, self.rename_button, self.delete_button):
            btn_row.addWidget(b)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # ---------------- 右：编辑 ----------------
        right = QWidget()
        form = QFormLayout(right)
        self.title = QLabel("")
        self.title.setStyleSheet("font-size: 16px; font-weight: 600;")
        form.addRow(self.title)
        self.description = QLineEdit()
        self.description.setPlaceholderText("一句话说明这个场景（可不填）")
        form.addRow("说明", self.description)

        self.asr_model = QComboBox()
        self.asr_model.addItem("（继承父场景）", _INHERIT)
        for mid, label in ASR_MODELS:
            if mid != "auto":
                self.asr_model.addItem(label, mid)
        form.addRow("识别模型", self.asr_model)

        tr_row = QHBoxLayout()
        self.translate_provider = QComboBox()
        self.translate_provider.addItem("（继承父场景）", _INHERIT)
        for key, label in TRANSLATE_PROVIDERS.items():
            self.translate_provider.addItem(label, key)
        self.translate_provider.currentIndexChanged.connect(self._fill_translate_models)
        self.translate_model = QComboBox()
        tr_row.addWidget(self.translate_provider)
        tr_row.addWidget(self.translate_model, 1)
        form.addRow("翻译模型", tr_row)
        self._fill_translate_models()

        self.asr_prompt = QPlainTextEdit()
        self.asr_prompt.setPlaceholderText("专有名词、人名、地图名……用逗号或换行分开。告诉识别模型这些词会出现，它就不容易听错。")
        self.asr_prompt.setMaximumHeight(70)
        form.addRow("识别提示词", self.asr_prompt)

        self.style = QLineEdit()
        self.style.setPlaceholderText("例如：电竞解说风格，简短口语化（留空则继承）")
        form.addRow("翻译风格", self.style)

        self.corrections = PairTable(("听错的词", "改成"))
        self.corrections.setMaximumHeight(140)
        corr_box = QVBoxLayout()
        corr_box.addWidget(self.corrections)
        corr_btns = QHBoxLayout()
        b = QPushButton("添加")
        b.clicked.connect(lambda: self.corrections.add_row())
        corr_btns.addWidget(b)
        b = QPushButton("删除选中")
        b.clicked.connect(self.corrections.remove_selected)
        corr_btns.addWidget(b)
        corr_btns.addStretch(1)
        corr_box.addLayout(corr_btns)
        form.addRow("纠错规则", corr_box)

        self.glossary = PairTable(("原文", "译文"))
        gl_box = QVBoxLayout()
        gl_box.addWidget(self.glossary, 1)
        gl_btns = QHBoxLayout()
        b = QPushButton("添加")
        b.clicked.connect(lambda: self.glossary.add_row())
        gl_btns.addWidget(b)
        b = QPushButton("删除选中")
        b.clicked.connect(self.glossary.remove_selected)
        gl_btns.addWidget(b)
        gl_btns.addSpacing(16)
        self.import_button = QPushButton("导入 CSV / Excel…")
        self.import_button.clicked.connect(self._import_glossary)
        gl_btns.addWidget(self.import_button)
        self.export_button = QPushButton("导出 CSV…")
        self.export_button.clicked.connect(self._export_glossary)
        gl_btns.addWidget(self.export_button)
        gl_btns.addStretch(1)
        gl_box.addLayout(gl_btns)
        form.addRow("术语表", gl_box)

        self.inherited = hint("")
        form.addRow("继承汇总", self.inherited)

        save_row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color: #2a7;")
        save_row.addWidget(self.status, 1)
        self.revert_button = QPushButton("放弃修改")
        self.revert_button.clicked.connect(lambda: self._load_profile(self._current))
        save_row.addWidget(self.revert_button)
        self.save_button = QPushButton("保存")
        self.save_button.setMinimumHeight(34)
        self.save_button.clicked.connect(self.save)
        save_row.addWidget(self.save_button)
        form.addRow("", save_row)

        splitter.addWidget(right)
        splitter.setSizes([230, 650])

        self.reload_tree()

    # ------------------------------------------------------------ 树
    def reload_tree(self, select: str | None = None) -> None:
        select = select or self._current or ROOT_NAME
        self.tree.blockSignals(True)
        self.tree.clear()
        items: dict[str, QTreeWidgetItem] = {}

        def add(name: str, parent_item: QTreeWidgetItem | None) -> None:
            item = QTreeWidgetItem([name])
            item.setData(0, Qt.ItemDataRole.UserRole, name)
            if parent_item is None:
                self.tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)
            items[name] = item
            for c in self.store.children(name):
                add(c.name, item)

        add(ROOT_NAME, None)
        self.tree.expandAll()
        self.tree.blockSignals(False)
        target = items.get(select) or items[ROOT_NAME]
        self.tree.setCurrentItem(target)
        self._load_profile(target.data(0, Qt.ItemDataRole.UserRole))

    def _on_tree_select(self, current: QTreeWidgetItem | None, _prev) -> None:
        if current is None:
            return
        name = current.data(0, Qt.ItemDataRole.UserRole)
        if name == self._current:
            return
        self._load_profile(name)

    def current_name(self) -> str | None:
        return self._current

    # ------------------------------------------------------------ 编辑区
    def _fill_translate_models(self) -> None:
        provider = self.translate_provider.currentData()
        self.translate_model.clear()
        self.translate_model.addItem("（继承父场景）", _INHERIT)
        for mid, label in TRANSLATE_MODELS.get(provider or "", []):
            self.translate_model.addItem(label, mid)
        self.translate_model.setEnabled(bool(provider))

    def _load_profile(self, name: str | None) -> None:
        p = self.store.get(name or ROOT_NAME)
        if p is None:
            return
        self._current = p.name
        self.title.setText(self.store.display_name(p.name))
        self.description.setText(p.description)
        self.asr_model.setCurrentIndex(max(0, self.asr_model.findData(p.asr_model or _INHERIT)))
        self.translate_provider.setCurrentIndex(max(0, self.translate_provider.findData(p.translate_provider or _INHERIT)))
        self._fill_translate_models()
        self.translate_model.setCurrentIndex(max(0, self.translate_model.findData(p.translate_model or _INHERIT)))
        self.asr_prompt.setPlainText(", ".join(p.asr_prompt))
        self.style.setText(p.style or "")
        self.corrections.set_pairs(p.corrections)
        self.glossary.set_pairs(p.glossary)
        self.status.setText("")
        is_root = p.name == ROOT_NAME
        self.rename_button.setEnabled(not is_root)
        self.delete_button.setEnabled(not is_root)
        self._update_inherited()

    def _update_inherited(self) -> None:
        if not self._current:
            return
        eff = self.store.resolve(self._current)
        own = self.store.get(self._current)
        inherited_terms = len(eff.glossary) - len(own.glossary if own else {})
        inherited_corr = len(eff.corrections) - len(own.corrections if own else {})
        parts = [f"合并后共 {len(eff.glossary)} 条术语（其中 {max(0, inherited_terms)} 条来自父场景）",
                 f"{len(eff.corrections)} 条纠错（{max(0, inherited_corr)} 条来自父场景）",
                 f"{len(eff.asr_prompt)} 个提示词"]
        if eff.style:
            parts.append(f"风格：{eff.style[:30]}{'…' if len(eff.style) > 30 else ''}")
        self.inherited.setText("；".join(parts))

    def _collect(self) -> Profile:
        old = self.store.get(self._current or ROOT_NAME) or Profile(name=self._current or ROOT_NAME)
        import re
        terms = [t.strip() for t in re.split(r"[,，;；\n]+", self.asr_prompt.toPlainText()) if t.strip()]
        return Profile(
            name=old.name,
            parent=old.parent,
            asr_model=self.asr_model.currentData() or None,
            translate_provider=self.translate_provider.currentData() or None,
            translate_model=self.translate_model.currentData() or None,
            asr_prompt=terms,
            corrections=self.corrections.pairs(),
            glossary=self.glossary.pairs(),
            style=self.style.text().strip() or None,
            description=self.description.text().strip(),
        )

    def save(self) -> None:
        if not self._current:
            return
        try:
            self.store.save(self._collect())
        except UserFacingError as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, "保存失败", f"写文件出错：{e}")
            return
        self.status.setText("已保存。")
        self._update_inherited()
        self.profiles_changed.emit()

    # ------------------------------------------------------------ 增删改名
    def _add_child(self) -> None:
        parent = self._current or ROOT_NAME
        name, ok = QInputDialog.getText(self, "新建子场景", f"在「{self.store.display_name(parent)}」下新建子场景，名字：")
        if not ok or not name.strip():
            return
        try:
            self.store.create_child(parent, name)
        except UserFacingError as e:
            QMessageBox.warning(self, "无法新建", str(e))
            return
        self.reload_tree(select=name.strip())
        self.profiles_changed.emit()

    def _rename(self) -> None:
        if not self._current or self._current == ROOT_NAME:
            return
        name, ok = QInputDialog.getText(self, "重命名", "新的名字：", text=self._current)
        if not ok or not name.strip() or name.strip() == self._current:
            return
        try:
            self.store.rename(self._current, name)
        except UserFacingError as e:
            QMessageBox.warning(self, "无法重命名", str(e))
            return
        self._current = name.strip()
        self.reload_tree(select=self._current)
        self.profiles_changed.emit()

    def _delete(self) -> None:
        if not self._current or self._current == ROOT_NAME:
            return
        kids = self.store.descendants(self._current)
        msg = f"确定删除场景「{self.store.display_name(self._current)}」？"
        if kids:
            msg += f"\n它下面的 {len(kids)} 个子场景也会一起删除。"
        if QMessageBox.question(self, "删除场景", msg) != QMessageBox.StandardButton.Yes:
            return
        parent = (self.store.get(self._current) or Profile(name="")).parent or ROOT_NAME
        try:
            self.store.delete(self._current)
        except UserFacingError as e:
            QMessageBox.warning(self, "无法删除", str(e))
            return
        self._current = None
        self.reload_tree(select=parent)
        self.profiles_changed.emit()

    # ------------------------------------------------------------ 导入导出
    def _import_glossary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "导入术语表", "", "表格文件 (*.csv *.xlsx);;所有文件 (*)")
        if not path:
            return
        try:
            pairs = import_pairs(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, "导入失败", friendly_message(e))
            return
        existing = self.glossary.pairs()
        added = sum(1 for k in pairs if k not in existing)
        existing.update(pairs)
        self.glossary.set_pairs(existing)
        self.status.setText(f"已导入 {len(pairs)} 条（新增 {added} 条），记得点「保存」。")

    def _export_glossary(self) -> None:
        default = f"{self._current or '术语表'}.csv"
        path, _ = QFileDialog.getSaveFileName(self, "导出术语表", default, "CSV 文件 (*.csv)")
        if not path:
            return
        try:
            export_csv(path, self.glossary.pairs())
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.status.setText(f"已导出到 {path}")
