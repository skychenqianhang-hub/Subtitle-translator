"""「让 AI 生成词表」对话框：填领域 → 后台联网生成 → 预览表（可删行）→ 加进场景的术语表。"""
from __future__ import annotations

from app.i18n import tr

from typing import Callable

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPushButton, QRadioButton,
    QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config import Config, GLOSSARY_LANG_NAMES
from app.core.errors import friendly_message
from app.core.profiles.generate import (
    CONFIDENCE_LABELS, DEFAULT_GENERATE_MODEL, DEFAULT_SEARCH_BUDGET, GENERATE_MODELS, SEARCH_BUDGETS, GenerateRequest,
    GlossaryDraft, estimate_cost_usd, generate_glossary,
)

BUDGET_LABELS = {"low": "省钱（最多搜 8 次）", "medium": "标准（最多搜 12 次）", "high": "充分（最多搜 20 次）"}
from app.core.profiles.glossary import GLOSSARY_LANGS, Row
from app.ui.common import hint, set_status

Generator = Callable[..., GlossaryDraft]      # generate_glossary 的签名；测试里换成假的


class _Worker(QObject):
    done = Signal(object)        # GlossaryDraft
    failed = Signal(str)
    progress = Signal(str)

    def __init__(self, generator: Generator, cfg: Config, req: GenerateRequest, model: str) -> None:
        super().__init__()
        self.generator, self.cfg, self.req, self.model = generator, cfg, req, model

    def run(self) -> None:
        try:
            draft = self.generator(self.cfg, self.req, model=self.model, progress=self.progress.emit)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_message(e))
            return
        self.done.emit(draft)


class GlossaryGenerateDialog(QDialog):
    """结果通过 accepted_rows / accepted_prompt / accepted_description 取。"""

    def __init__(self, cfg: Config, scene_display: str, existing_rows: list[Row], default_domain: str = "",
                 parent: QWidget | None = None, generator: Generator = generate_glossary) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.existing_rows = existing_rows
        self.generator = generator
        self.draft: GlossaryDraft | None = None
        self.accepted_rows: list[Row] = []
        self.accepted_prompt: list[str] = []
        self.accepted_description = ""
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self.setWindowTitle(tr("让 AI 生成词表 - {0}", scene_display))
        self.resize(960, 680)

        layout = QVBoxLayout(self)
        layout.addWidget(hint(tr("模型会联网查官方资料（官网各语言页面、维基、片方官网），整理成多语言术语表并附来源。"
                                 "结果先在这里预览，你删掉不要的行后再加进场景；没把握的词会标出来，建议过目。")))

        # ---- 参数 ----
        form_row = QHBoxLayout()
        form_row.addWidget(QLabel(tr("领域")))
        self.domain = QLineEdit(default_domain)
        self.domain.setPlaceholderText(tr("一句话描述，例如：英雄联盟；电影《沙丘 2》；日本职业棒球"))
        form_row.addWidget(self.domain, 1)
        layout.addLayout(form_row)

        lang_row = QHBoxLayout()
        lang_row.addWidget(QLabel(tr("语言列")))
        self.lang_checks: dict[str, QCheckBox] = {}
        default_langs = {"en", "ja", cfg.target_language if cfg.target_language in GLOSSARY_LANGS else "zh-Hans",
                         "zh-Hans", "zh-Hant"}
        for lang in GLOSSARY_LANGS:
            cb = QCheckBox(tr(GLOSSARY_LANG_NAMES[lang]))
            cb.setChecked(lang in default_langs)
            cb.toggled.connect(self._update_estimate)
            self.lang_checks[lang] = cb
            lang_row.addWidget(cb)
        lang_row.addSpacing(16)
        lang_row.addWidget(QLabel(tr("模型")))
        self.model = QComboBox()
        for mid, label in GENERATE_MODELS:
            self.model.addItem(tr(label), mid)
        default_model = cfg.translate_model if cfg.translate_provider == "anthropic" else DEFAULT_GENERATE_MODEL
        self.model.setCurrentIndex(max(0, self.model.findData(default_model)))
        self.model.currentIndexChanged.connect(self._update_estimate)
        lang_row.addWidget(self.model)
        lang_row.addSpacing(16)
        lang_row.addWidget(QLabel(tr("联网预算")))
        self.budget = QComboBox()
        for key, label in BUDGET_LABELS.items():
            self.budget.addItem(tr(label), key)
        self.budget.setCurrentIndex(max(0, self.budget.findData(DEFAULT_SEARCH_BUDGET)))
        self.budget.currentIndexChanged.connect(self._update_estimate)
        lang_row.addWidget(self.budget)
        lang_row.addSpacing(16)
        lang_row.addWidget(QLabel(tr("最多")))
        self.max_terms = QSpinBox()
        self.max_terms.setRange(20, 300)
        self.max_terms.setValue(120)
        self.max_terms.setSuffix(tr(" 条"))
        self.max_terms.valueChanged.connect(self._update_estimate)
        lang_row.addWidget(self.max_terms)
        lang_row.addStretch(1)
        layout.addLayout(lang_row)

        mode_row = QHBoxLayout()
        self.mode_new = QRadioButton(tr("新建词表"))
        self.mode_fill = QRadioButton(tr("只补全现有表里空着的格（{0} 行）", len(existing_rows)))
        self.mode_new.setChecked(True)
        self.mode_fill.setEnabled(bool(existing_rows))
        self.mode_fill.toggled.connect(self._on_mode)
        mode_row.addWidget(self.mode_new)
        mode_row.addWidget(self.mode_fill)
        mode_row.addStretch(1)
        layout.addLayout(mode_row)

        self.estimate = hint("")
        layout.addWidget(self.estimate)

        run_row = QHBoxLayout()
        self.start_button = QPushButton(tr("开始生成"))
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumHeight(34)
        self.start_button.clicked.connect(self.start)
        run_row.addWidget(self.start_button)
        self.status = QLabel("")
        run_row.addWidget(self.status, 1)
        layout.addLayout(run_row)

        # ---- 结果 ----
        self.table = QTableWidget(0, len(GLOSSARY_LANGS) + 2)
        self.table.setHorizontalHeaderLabels([tr(GLOSSARY_LANG_NAMES[lang]) for lang in GLOSSARY_LANGS]
                                             + [tr("把握"), tr("来源")])
        for i in range(len(GLOSSARY_LANGS)):
            self.table.horizontalHeader().setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(len(GLOSSARY_LANGS) + 1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

        table_btns = QHBoxLayout()
        self.remove_button = QPushButton(tr("删除选中"))
        self.remove_button.clicked.connect(self._remove_selected)
        table_btns.addWidget(self.remove_button)
        self.remove_unsure_button = QPushButton(tr("删掉所有「没把握」的行"))
        self.remove_unsure_button.clicked.connect(self._remove_unsure)
        table_btns.addWidget(self.remove_unsure_button)
        table_btns.addStretch(1)
        self.summary = hint("")
        table_btns.addWidget(self.summary)
        layout.addLayout(table_btns)

        self.use_prompt = QCheckBox(tr("把专有名词加进识别提示词"))
        self.use_prompt.setChecked(True)
        self.use_description = QCheckBox(tr("场景说明为空时填入 AI 写的说明"))
        self.use_description.setChecked(True)
        layout.addWidget(self.use_prompt)
        layout.addWidget(self.use_description)

        self.buttons = QDialogButtonBox()
        self.accept_button = self.buttons.addButton(tr("加进术语表"), QDialogButtonBox.ButtonRole.AcceptRole)
        self.accept_button.setObjectName("primary")
        self.buttons.addButton(tr("取消"), QDialogButtonBox.ButtonRole.RejectRole)
        self.buttons.accepted.connect(self._accept)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        self._set_result_enabled(False)
        self._update_estimate()

    # ------------------------------------------------------------ 参数
    def selected_languages(self) -> list[str]:
        return [lang for lang, cb in self.lang_checks.items() if cb.isChecked()]

    def _on_mode(self) -> None:
        fill = self.mode_fill.isChecked()
        self.max_terms.setEnabled(not fill)
        self._update_estimate()

    def _update_estimate(self) -> None:
        n = len(self.existing_rows) if self.mode_fill.isChecked() else self.max_terms.value()
        searches = SEARCH_BUDGETS.get(self.budget.currentData() or DEFAULT_SEARCH_BUDGET, 12)
        low, high = estimate_cost_usd(self.model.currentData() or DEFAULT_GENERATE_MODEL, n, searches)
        self.estimate.setText(tr("这个功能固定用 Claude，需要 Anthropic 的 API Key。费用大约 ${0:.2f} ～ ${1:.2f}：联网搜索每次 $0.01，加上正常的字数费。",
                                 low, high))

    # ------------------------------------------------------------ 运行
    def start(self) -> None:
        langs = self.selected_languages()
        if not self.domain.text().strip():
            self.status.setText(tr("请先写一句话描述这个领域。"))
            return
        if len(langs) < 2:
            self.status.setText(tr("至少勾两种语言。"))
            return
        if not self.cfg.has_anthropic_key():
            set_status(self.status, "error")
            self.status.setText(tr("还没有填 Anthropic 的 API Key。请到右上角「设置 → API Key」填写。"))
            return
        set_status(self.status, "plain")
        req = GenerateRequest(
            domain=self.domain.text().strip(), languages=langs, max_terms=self.max_terms.value(),
            existing_rows=list(self.existing_rows) if self.mode_fill.isChecked() else [],
            ui_language=self.cfg.ui_language or "zh",
            max_searches=SEARCH_BUDGETS.get(self.budget.currentData() or DEFAULT_SEARCH_BUDGET, 12),
        )
        self._set_running(True)
        self.status.setText(tr("正在联网查资料并整理（通常要一到三分钟）……"))
        self._worker = _Worker(self.generator, self.cfg, req, self.model.currentData() or DEFAULT_GENERATE_MODEL)
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self.status.setText)
        self._worker.done.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.done.connect(self._thread.quit)
        self._worker.failed.connect(self._thread.quit)
        self._thread.start()

    def _set_running(self, running: bool) -> None:
        for w in (self.start_button, self.domain, self.max_terms, self.mode_new, self.mode_fill, self.model, self.budget,
                  *self.lang_checks.values()):
            w.setEnabled(not running)
        if not running:
            self._on_mode()

    def _set_result_enabled(self, on: bool) -> None:
        for w in (self.table, self.remove_button, self.remove_unsure_button, self.accept_button, self.use_prompt,
                  self.use_description):
            w.setEnabled(on)

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        set_status(self.status, "error")
        self.status.setText(message)

    def _on_done(self, draft: GlossaryDraft) -> None:
        self._set_running(False)
        self.draft = draft
        set_status(self.status, "ok")
        self.status.setText(tr("完成：{0} 条，联网搜索 {1} 次、抓取网页 {2} 次，本次费用约 ${3:.3f}", len(draft.rows),
                               draft.searches, draft.fetches, draft.cost_usd()))
        self.table.setRowCount(0)
        for d in draft.rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for i, lang in enumerate(GLOSSARY_LANGS):
                self.table.setItem(r, i, QTableWidgetItem(d.terms.get(lang, "")))
            conf = QTableWidgetItem(tr(CONFIDENCE_LABELS.get(d.confidence, "没把握")))
            conf.setData(Qt.ItemDataRole.UserRole, d.confidence)
            conf.setFlags(conf.flags() & ~Qt.ItemFlag.ItemIsEditable)
            if d.confidence == "unsure":
                conf.setForeground(Qt.GlobalColor.red)
            self.table.setItem(r, len(GLOSSARY_LANGS), conf)
            src = QTableWidgetItem(d.source)
            src.setToolTip(d.source)
            src.setFlags(src.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(r, len(GLOSSARY_LANGS) + 1, src)
        self._set_result_enabled(True)
        self._update_summary()

    # ------------------------------------------------------------ 结果表
    def _update_summary(self) -> None:
        unsure = sum(1 for r in range(self.table.rowCount())
                     if (self.table.item(r, len(GLOSSARY_LANGS)) or QTableWidgetItem()).data(Qt.ItemDataRole.UserRole) == "unsure")
        self.summary.setText(tr("{0} 行，其中 {1} 行没把握", self.table.rowCount(), unsure))

    def _remove_selected(self) -> None:
        for r in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(r)
        self._update_summary()

    def _remove_unsure(self) -> None:
        for r in range(self.table.rowCount() - 1, -1, -1):
            item = self.table.item(r, len(GLOSSARY_LANGS))
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == "unsure":
                self.table.removeRow(r)
        self._update_summary()

    def rows(self) -> list[Row]:
        out: list[Row] = []
        for r in range(self.table.rowCount()):
            row = {}
            for i, lang in enumerate(GLOSSARY_LANGS):
                text = (self.table.item(r, i).text() if self.table.item(r, i) else "").strip()
                if text:
                    row[lang] = text
            if row:
                out.append(row)
        return out

    def _accept(self) -> None:
        if self.draft is None:
            return
        self.accepted_rows = self.rows()
        self.accepted_prompt = list(self.draft.asr_prompt) if self.use_prompt.isChecked() else []
        self.accepted_description = self.draft.description if self.use_description.isChecked() else ""
        self.accept()
