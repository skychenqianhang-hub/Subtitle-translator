"""设置页：API Key、默认模型、源语言。保存到 %APPDATA%\\SubTranslator\\config.json。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from app.config import (
    ASR_MODELS, SOURCE_LANGUAGES, TRANSLATE_MODELS, TRANSLATE_PROVIDERS, Config, config_path, save_config,
)
from app.ui.common import hint, page_title


class SettingsPage(QWidget):
    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.addWidget(page_title("设置"))

        key_box = QGroupBox("API Key")
        key_form = QFormLayout(key_box)
        self.openai_key, openai_row = self._key_field("sk-...")
        self.anthropic_key, anthropic_row = self._key_field("sk-ant-...")
        key_form.addRow("OpenAI（语音识别 / GPT 翻译）", openai_row)
        key_form.addRow("Anthropic（Claude 翻译）", anthropic_row)
        key_form.addRow("", hint(f"Key 只保存在你自己电脑的这个文件里，不会进入项目代码：\n{config_path()}"))
        layout.addWidget(key_box)

        model_box = QGroupBox("默认模型")
        model_form = QFormLayout(model_box)
        self.asr_model = QComboBox()
        self.asr_model.setEditable(True)
        self.asr_model.addItems(ASR_MODELS)
        self.translate_provider = QComboBox()
        for key, label in TRANSLATE_PROVIDERS.items():
            self.translate_provider.addItem(label, key)
        self.translate_provider.currentIndexChanged.connect(self._refresh_translate_models)
        self.translate_model = QComboBox()
        self.translate_model.setEditable(True)
        model_form.addRow("识别模型（OpenAI）", self.asr_model)
        model_form.addRow("翻译服务", self.translate_provider)
        model_form.addRow("翻译模型", self.translate_model)
        model_form.addRow("", hint("这里是全局默认值；每个场景可以在「场景管理」里单独指定模型。模型名称可以手动输入。"))
        layout.addWidget(model_box)

        lang_box = QGroupBox("语言")
        lang_form = QFormLayout(lang_box)
        self.source_language = QComboBox()
        for key, label in SOURCE_LANGUAGES.items():
            self.source_language.addItem(label, key)
        lang_form.addRow("源语言", self.source_language)
        lang_form.addRow("目标语言", QLabel("简体中文"))
        layout.addWidget(lang_box)

        save_row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color: #2a7;")
        save_row.addWidget(self.status, 1)
        self.save_button = QPushButton("保存设置")
        self.save_button.setMinimumHeight(36)
        self.save_button.clicked.connect(self.save)
        save_row.addWidget(self.save_button)
        layout.addLayout(save_row)
        layout.addStretch(1)

        self.load_from_config()

    def _key_field(self, placeholder: str) -> tuple[QLineEdit, QWidget]:
        edit = QLineEdit()
        edit.setPlaceholderText(placeholder)
        edit.setEchoMode(QLineEdit.EchoMode.Password)
        toggle = QToolButton()
        toggle.setText("显示")
        toggle.setCheckable(True)
        toggle.toggled.connect(
            lambda on: edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password)
        )
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(edit, 1)
        row_layout.addWidget(toggle)
        return edit, row

    def _refresh_translate_models(self) -> None:
        provider = self.translate_provider.currentData()
        self.translate_model.clear()
        self.translate_model.addItems(TRANSLATE_MODELS.get(provider, []))
        if provider == self.cfg.translate_provider and self.cfg.translate_model:
            self.translate_model.setCurrentText(self.cfg.translate_model)

    def load_from_config(self) -> None:
        cfg = self.cfg
        self.openai_key.setText(cfg.openai_api_key)
        self.anthropic_key.setText(cfg.anthropic_api_key)
        self.asr_model.setCurrentText(cfg.asr_model)
        idx = self.translate_provider.findData(cfg.translate_provider)
        self.translate_provider.setCurrentIndex(max(0, idx))
        self._refresh_translate_models()
        idx = self.source_language.findData(cfg.source_language)
        self.source_language.setCurrentIndex(max(0, idx))

    def save(self) -> None:
        cfg = self.cfg
        cfg.openai_api_key = self.openai_key.text().strip()
        cfg.anthropic_api_key = self.anthropic_key.text().strip()
        cfg.asr_model = self.asr_model.currentText().strip()
        cfg.translate_provider = self.translate_provider.currentData()
        cfg.translate_model = self.translate_model.currentText().strip()
        cfg.source_language = self.source_language.currentData()
        try:
            save_config(cfg)
        except OSError as e:
            self.status.setStyleSheet("color: #c33;")
            self.status.setText(f"保存失败：{e}")
            return
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText("已保存。")
