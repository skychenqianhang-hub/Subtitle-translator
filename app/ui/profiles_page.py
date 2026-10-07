"""场景管理页：左侧场景树，右侧编辑该场景自己的设置（继承来的另外显示）。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog, QLabel, QLineEdit,
    QMessageBox, QPlainTextEdit, QPushButton, QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.config import ASR_MODELS, GLOSSARY_LANG_NAMES, TRANSLATE_MODELS, TRANSLATE_PROVIDERS
from app.core.errors import UserFacingError, friendly_message
from app.core.profiles.glossary import GLOSSARY_LANGS, Row, merge_rows
from app.core.profiles.glossary_io import export_glossary, import_glossary
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


class GlossaryTable(QTableWidget):
    """多语言术语表：一列一种语言，一行是同一个词在各语言里的写法。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, len(GLOSSARY_LANGS), parent)
        self.setHorizontalHeaderLabels([tr(GLOSSARY_LANG_NAMES[lang]) for lang in GLOSSARY_LANGS])
        for i in range(len(GLOSSARY_LANGS)):
            self.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.verticalHeader().setVisible(False)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)

    def set_rows(self, rows: list[Row]) -> None:
        self.setRowCount(0)
        for r in rows:
            self.add_row(r)

    def add_row(self, row: Row | None = None) -> None:
        r = self.rowCount()
        self.insertRow(r)
        for i, lang in enumerate(GLOSSARY_LANGS):
            self.setItem(r, i, QTableWidgetItem((row or {}).get(lang, "")))
        if not row:
            self.setCurrentCell(r, 0)
            self.editItem(self.item(r, 0))

    def remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.selectedIndexes()}, reverse=True):
            self.removeRow(r)

    def rows(self) -> list[Row]:
        out: list[Row] = []
        for r in range(self.rowCount()):
            row = {}
            for i, lang in enumerate(GLOSSARY_LANGS):
                text = (self.item(r, i).text() if self.item(r, i) else "").strip()
                if text:
                    row[lang] = text
            if row:
                out.append(row)
        return out


class ProfilesPage(QWidget):
    profiles_changed = Signal()   # 场景树或内容有变化（给主页的选择器刷新用）

    def __init__(self, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.store = store
        self._current: str | None = None
        self._dirty = False

        layout = QVBoxLayout(self)
        layout.addWidget(page_title(tr("场景管理")))
        layout.addWidget(hint(tr("场景是树状的：子场景自动继承父场景的全部设置。术语表、纠错规则、专有名词提示是「合并」继承，子场景只需要填自己多出来的部分；同一个词子场景的写法优先。")))

        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        # ---------------- 左：场景树 ----------------
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel(tr("场景"))
        self.tree.currentItemChanged.connect(self._on_tree_select)
        left_layout.addWidget(self.tree, 1)
        btn_row = QHBoxLayout()
        self.add_button = QPushButton(tr("新建子场景"))
        self.add_button.clicked.connect(self._add_child)
        self.rename_button = QPushButton(tr("重命名"))
        self.rename_button.clicked.connect(self._rename)
        self.delete_button = QPushButton(tr("删除"))
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
        self.description.setPlaceholderText(tr("一句话说明这个场景（可不填）"))
        form.addRow(tr("说明"), self.description)

        self.asr_model = QComboBox()
        self.asr_model.addItem(tr("（继承父场景）"), _INHERIT)
        for mid, label in ASR_MODELS:
            if mid != "auto":
                self.asr_model.addItem(tr(label), mid)
        form.addRow(tr("识别模型"), self.asr_model)

        tr_row = QHBoxLayout()
        self.translate_provider = QComboBox()
        self.translate_provider.addItem(tr("（继承父场景）"), _INHERIT)
        for key, label in TRANSLATE_PROVIDERS.items():
            self.translate_provider.addItem(tr(label), key)
        self.translate_provider.currentIndexChanged.connect(self._fill_translate_models)
        self.translate_model = QComboBox()
        tr_row.addWidget(self.translate_provider)
        tr_row.addWidget(self.translate_model, 1)
        form.addRow(tr("翻译模型"), tr_row)
        self._fill_translate_models()

        self.asr_prompt = QPlainTextEdit()
        self.asr_prompt.setPlaceholderText(tr("专有名词、人名、地图名……用逗号或换行分开。告诉识别模型这些词会出现，它就不容易听错。"))
        self.asr_prompt.setMaximumHeight(70)
        form.addRow(tr("识别提示词"), self.asr_prompt)

        self.style = QLineEdit()
        self.style.setPlaceholderText(tr("例如：电竞解说风格，简短口语化（留空则继承）"))
        form.addRow(tr("翻译风格"), self.style)

        self.corrections = PairTable((tr("听错的词"), tr("改成")))
        self.corrections.setMaximumHeight(140)
        corr_box = QVBoxLayout()
        corr_box.addWidget(self.corrections)
        corr_btns = QHBoxLayout()
        b = QPushButton(tr("添加"))
        b.clicked.connect(lambda: self.corrections.add_row())
        corr_btns.addWidget(b)
        b = QPushButton(tr("删除选中"))
        b.clicked.connect(self.corrections.remove_selected)
        corr_btns.addWidget(b)
        corr_btns.addStretch(1)
        corr_box.addLayout(corr_btns)
        form.addRow(tr("纠错规则"), corr_box)

        self.glossary = GlossaryTable()
        gl_box = QVBoxLayout()
        gl_box.addWidget(hint(tr("一行是同一个词在各语言里的写法。翻译时按主页的「原文语言 → 翻译至」取对应两列；哪一格留空就不管那个方向。")))
        gl_box.addWidget(self.glossary, 1)
        gl_btns = QHBoxLayout()
        b = QPushButton(tr("添加"))
        b.clicked.connect(lambda: self.glossary.add_row())
        gl_btns.addWidget(b)
        b = QPushButton(tr("删除选中"))
        b.clicked.connect(self.glossary.remove_selected)
        gl_btns.addWidget(b)
        gl_btns.addSpacing(16)
        self.import_button = QPushButton(tr("导入 CSV / Excel…"))
        self.import_button.clicked.connect(self._import_glossary)
        gl_btns.addWidget(self.import_button)
        self.export_button = QPushButton(tr("导出 CSV…"))
        self.export_button.clicked.connect(self._export_glossary)
        gl_btns.addWidget(self.export_button)
        gl_btns.addStretch(1)
        gl_box.addLayout(gl_btns)
        form.addRow(tr("术语表"), gl_box)

        self.inherited = hint("")
        form.addRow(tr("继承汇总"), self.inherited)

        save_row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color: #2a7;")
        save_row.addWidget(self.status, 1)
        self.revert_button = QPushButton(tr("放弃修改"))
        self.revert_button.clicked.connect(lambda: self._load_profile(self._current))
        save_row.addWidget(self.revert_button)
        self.save_button = QPushButton(tr("保存"))
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
            item = QTreeWidgetItem([tr(name)])
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
        self.translate_model.addItem(tr("（继承父场景）"), _INHERIT)
        for mid, label in TRANSLATE_MODELS.get(provider or "", []):
            self.translate_model.addItem(tr(label), mid)
        self.translate_model.setEnabled(bool(provider))

    def _load_profile(self, name: str | None) -> None:
        p = self.store.get(name or ROOT_NAME)
        if p is None:
            return
        self._current = p.name
        self.title.setText(self.store.display_name(p.name))
        self.description.setText(tr(p.description))     # 预置场景的说明有翻译；自己写的原样显示
        self.asr_model.setCurrentIndex(max(0, self.asr_model.findData(p.asr_model or _INHERIT)))
        self.translate_provider.setCurrentIndex(max(0, self.translate_provider.findData(p.translate_provider or _INHERIT)))
        self._fill_translate_models()
        self.translate_model.setCurrentIndex(max(0, self.translate_model.findData(p.translate_model or _INHERIT)))
        self.asr_prompt.setPlainText(", ".join(p.asr_prompt))
        self.style.setText(p.style or "")
        self.corrections.set_pairs(p.corrections)
        self.glossary.set_rows(p.glossary)
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
        parts = [tr("合并后共 {0} 条术语（其中 {1} 条来自父场景）", len(eff.glossary), max(0, inherited_terms)),
                 tr("{0} 条纠错（{1} 条来自父场景）", len(eff.corrections), max(0, inherited_corr)),
                 tr("{0} 个提示词", len(eff.asr_prompt))]
        if eff.style:
            parts.append(tr("风格：{0}{1}", eff.style[:30], '…' if len(eff.style) > 30 else ''))
        self.inherited.setText(tr("；").join(parts))

    def _collect(self) -> Profile:
        old = self.store.get(self._current or ROOT_NAME) or Profile(name=self._current or ROOT_NAME)
        import re
        terms = [t.strip() for t in re.split(r"[,，;；\n]+", self.asr_prompt.toPlainText()) if t.strip()]
        description = self.description.text().strip()
        if description == tr(old.description):
            description = old.description      # 没改过：存回原文，不把翻译后的说明写进场景文件
        return Profile(
            name=old.name,
            parent=old.parent,
            asr_model=self.asr_model.currentData() or None,
            translate_provider=self.translate_provider.currentData() or None,
            translate_model=self.translate_model.currentData() or None,
            asr_prompt=terms,
            corrections=self.corrections.pairs(),
            glossary=self.glossary.rows(),
            style=self.style.text().strip() or None,
            description=description,
        )

    def save(self) -> None:
        if not self._current:
            return
        try:
            self.store.save(self._collect())
        except UserFacingError as e:
            QMessageBox.warning(self, tr("保存失败"), str(e))
            return
        except OSError as e:
            QMessageBox.warning(self, tr("保存失败"), tr("写文件出错：{0}", e))
            return
        self.status.setText(tr("已保存。"))
        self._update_inherited()
        self.profiles_changed.emit()

    # ------------------------------------------------------------ 增删改名
    def _add_child(self) -> None:
        parent = self._current or ROOT_NAME
        name, ok = QInputDialog.getText(self, tr("新建子场景"), tr("在「{0}」下新建子场景，名字：", self.store.display_name(parent)))
        if not ok or not name.strip():
            return
        try:
            self.store.create_child(parent, name)
        except UserFacingError as e:
            QMessageBox.warning(self, tr("无法新建"), str(e))
            return
        self.reload_tree(select=name.strip())
        self.profiles_changed.emit()

    def _rename(self) -> None:
        if not self._current or self._current == ROOT_NAME:
            return
        name, ok = QInputDialog.getText(self, tr("重命名"), tr("新的名字："), text=self._current)
        if not ok or not name.strip() or name.strip() == self._current:
            return
        try:
            self.store.rename(self._current, name)
        except UserFacingError as e:
            QMessageBox.warning(self, tr("无法重命名"), str(e))
            return
        self._current = name.strip()
        self.reload_tree(select=self._current)
        self.profiles_changed.emit()

    def _delete(self) -> None:
        if not self._current or self._current == ROOT_NAME:
            return
        kids = self.store.descendants(self._current)
        msg = tr("确定删除场景「{0}」？", self.store.display_name(self._current))
        if kids:
            msg += tr("\n它下面的 {0} 个子场景也会一起删除。", len(kids))
        if QMessageBox.question(self, tr("删除场景"), msg) != QMessageBox.StandardButton.Yes:
            return
        parent = (self.store.get(self._current) or Profile(name="")).parent or ROOT_NAME
        try:
            self.store.delete(self._current)
        except UserFacingError as e:
            QMessageBox.warning(self, tr("无法删除"), str(e))
            return
        self._current = None
        self.reload_tree(select=parent)
        self.profiles_changed.emit()

    # ------------------------------------------------------------ 导入导出
    def _import_glossary(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("导入术语表"), "", tr("表格文件 (*.csv *.xlsx);;所有文件 (*)"))
        if not path:
            return
        try:
            rows = import_glossary(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("导入失败"), friendly_message(e))
            return
        existing = self.glossary.rows()
        merged = merge_rows(existing, rows)
        self.glossary.set_rows(merged)
        self.status.setText(tr("已导入 {0} 条（新增 {1} 条），记得点「保存」。", len(rows), max(0, len(merged) - len(existing))))

    def _export_glossary(self) -> None:
        default = f"{self._current or '术语表'}.csv"
        path, _ = QFileDialog.getSaveFileName(self, tr("导出术语表"), default, tr("CSV 文件 (*.csv)"))
        if not path:
            return
        try:
            export_glossary(path, self.glossary.rows(), {lang: tr(name) for lang, name in GLOSSARY_LANG_NAMES.items()})
        except OSError as e:
            QMessageBox.warning(self, tr("导出失败"), str(e))
            return
        self.status.setText(tr("已导出到 {0}", path))
