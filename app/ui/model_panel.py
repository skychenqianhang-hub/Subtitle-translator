"""语言与模型：原文语言、翻译至、识别模型、翻译服务与模型。

实时翻译和视频翻译两页各放一个，但背后是同一份设置：在一页改了，另一页跟着变。
界面上分两块放：lang_widget（原文 → 译成，放在主卡片里）和 advanced_widget（模型，放在「高级」折叠区里）。
"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QWidget

from app.config import (
    ASR_AUTO, ASR_MODELS, DEFAULT_TRANSLATE_MODEL, SOURCE_LANGUAGES, TARGET_LANGUAGES, TRANSLATE_MODELS,
    TRANSLATE_PROVIDERS, Config, save_config,
)
from app.ui.common import hint


class ModelLanguagePanel(QWidget):
    changed = Signal()

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._loading = False

        # ---- 原文 → 译成 ----
        self.lang_widget = QWidget()
        lang_row = QHBoxLayout(self.lang_widget)
        lang_row.setContentsMargins(0, 0, 0, 0)
        lang_row.setSpacing(8)
        self.source_language = QComboBox()
        self.source_language.setToolTip(tr("视频里说的是什么语言。「自动检测」让识别模型自己判断。"))
        for key, label in SOURCE_LANGUAGES.items():
            self.source_language.addItem(tr(label), key)
        self.target_language = QComboBox()
        self.target_language.setToolTip(tr("字幕翻译成什么语言。"))
        for key, label in TARGET_LANGUAGES.items():
            self.target_language.addItem(tr(label), key)
        lang_row.addWidget(QLabel(tr("原文")))
        lang_row.addWidget(self.source_language)
        self.target_label = QLabel("→")
        lang_row.addWidget(self.target_label)
        lang_row.addWidget(self.target_language)

        # ---- 模型（高级）----
        self.advanced_widget = QWidget()
        form = QFormLayout(self.advanced_widget)
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.asr_model = QComboBox()
        for mid, label in ASR_MODELS:
            self.asr_model.addItem(tr(label), mid)
        form.addRow(tr("识别模型"), self.asr_model)
        tr_row = QHBoxLayout()
        tr_row.setSpacing(8)
        self.translate_provider = QComboBox()
        for key, label in TRANSLATE_PROVIDERS.items():
            self.translate_provider.addItem(tr(label), key)
        self.translate_model = QComboBox()
        tr_row.addWidget(self.translate_provider)
        tr_row.addWidget(self.translate_model, 1)
        self.translate_row_label = QLabel(tr("翻译模型"))
        form.addRow(self.translate_row_label, tr_row)
        form.addRow("", hint(tr("价格是每百万字的输入 / 输出费用。每个场景也可以在「管理场景」里单独指定模型，优先级高于这里。")))

        self.load_from_config()

        self.source_language.currentIndexChanged.connect(self._on_change)
        self.target_language.currentIndexChanged.connect(self._on_change)
        self.asr_model.currentIndexChanged.connect(self._on_change)
        self.translate_provider.currentIndexChanged.connect(self._on_provider_change)
        self.translate_model.currentIndexChanged.connect(self._on_change)

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802  两块控件各自放在页面不同位置，一起启停
        self.lang_widget.setEnabled(enabled)
        self.advanced_widget.setEnabled(enabled)
        super().setEnabled(enabled)

    # ---- 读写 ----
    def load_from_config(self) -> None:
        self._loading = True
        cfg = self.cfg
        self.source_language.setCurrentIndex(max(0, self.source_language.findData(cfg.source_language)))
        self.target_language.setCurrentIndex(max(0, self.target_language.findData(cfg.target_language)))
        self._select(self.asr_model, cfg.asr_model)
        self.translate_provider.setCurrentIndex(max(0, self.translate_provider.findData(cfg.translate_provider)))
        self._fill_translate_models(cfg.translate_provider)
        self._select(self.translate_model, cfg.translate_model)
        self._loading = False

    @staticmethod
    def _select(combo: QComboBox, model_id: str) -> None:
        idx = combo.findData(model_id)
        if idx < 0 and model_id:
            # 设置里是列表外的模型名（比如以前手动输入的）：原样加进去
            combo.addItem(model_id, model_id)
            idx = combo.count() - 1
        combo.setCurrentIndex(max(0, idx))

    def _fill_translate_models(self, provider: str) -> None:
        self.translate_model.blockSignals(True)
        self.translate_model.clear()
        for mid, label in TRANSLATE_MODELS.get(provider, []):
            self.translate_model.addItem(tr(label), mid)
        self.translate_model.blockSignals(False)

    def _on_provider_change(self) -> None:
        if self._loading:
            return
        provider = self.translate_provider.currentData()
        self._fill_translate_models(provider)
        self._select(self.translate_model, DEFAULT_TRANSLATE_MODEL.get(provider, ""))
        self._on_change()

    def _on_change(self) -> None:
        if self._loading:
            return
        cfg = self.cfg
        cfg.source_language = self.source_language.currentData()
        cfg.target_language = self.target_language.currentData()
        cfg.asr_model = self.asr_model.currentData() or ASR_AUTO
        cfg.translate_provider = self.translate_provider.currentData()
        cfg.translate_model = self.translate_model.currentData() or ""
        try:
            save_config(cfg)
        except OSError:
            pass
        self.changed.emit()

    # ---- 仅原文时不需要翻译 ----
    def set_translation_enabled(self, enabled: bool) -> None:
        for w in (self.target_label, self.target_language, self.translate_row_label,
                  self.translate_provider, self.translate_model):
            w.setEnabled(enabled)
