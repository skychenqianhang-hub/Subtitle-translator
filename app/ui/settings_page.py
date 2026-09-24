"""设置页：只放 API Key。模型和语言在主页上选。保存到 %APPDATA%\\SubTranslator\\config.json。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton, QVBoxLayout,
    QWidget,
)

from app.config import Config, config_path, save_config
from app.ui.common import hint, page_title


class SettingsPage(QWidget):
    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.addWidget(page_title("API Key"))
        layout.addWidget(hint("语音识别用 OpenAI；翻译按主页上选的翻译服务，用 Claude 就填 Anthropic 的 Key，用 GPT 就填 OpenAI 的 Key。"))

        key_box = QGroupBox("")
        key_form = QFormLayout(key_box)
        self.openai_key, openai_row = self._key_field("sk-...")
        self.anthropic_key, anthropic_row = self._key_field("sk-ant-...")
        key_form.addRow("OpenAI", openai_row)
        key_form.addRow("Anthropic", anthropic_row)
        key_form.addRow("", hint(f"Key 只保存在你自己电脑的这个文件里，不会进入项目代码：\n{config_path()}"))
        layout.addWidget(key_box)

        save_row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setStyleSheet("color: #2a7;")
        save_row.addWidget(self.status, 1)
        self.save_button = QPushButton("保存")
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

    def load_from_config(self) -> None:
        self.openai_key.setText(self.cfg.openai_api_key)
        self.anthropic_key.setText(self.cfg.anthropic_api_key)

    def save(self) -> None:
        self.cfg.openai_api_key = self.openai_key.text().strip()
        self.cfg.anthropic_api_key = self.anthropic_key.text().strip()
        try:
            save_config(self.cfg)
        except OSError as e:
            self.status.setStyleSheet("color: #c33;")
            self.status.setText(f"保存失败：{e}")
            return
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText("已保存。")
