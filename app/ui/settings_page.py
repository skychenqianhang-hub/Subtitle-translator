"""设置页：只放 API Key。模型和语言在主页上选。保存到 %APPDATA%\\SubTranslator\\config.json。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QPushButton, QToolButton,
    QVBoxLayout, QWidget,
)

from app.config import Config, config_path, default_download_dir, save_config
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

        dl_box = QGroupBox("网址下载")
        dl_form = QFormLayout(dl_box)
        dl_row = QHBoxLayout()
        self.download_dir = QLineEdit()
        self.download_dir.setPlaceholderText(str(default_download_dir()))
        self.download_button = QPushButton("选择文件夹…")
        self.download_button.clicked.connect(self._choose_download_dir)
        dl_row.addWidget(self.download_dir, 1)
        dl_row.addWidget(self.download_button)
        dl_form.addRow("保存位置", dl_row)
        dl_form.addRow("", hint("粘贴视频网址处理时，视频会先下载到这里，字幕文件也会生成在同一个文件夹。留空用默认位置。"))
        layout.addWidget(dl_box)

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

    def _choose_download_dir(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "选择下载保存位置", self.download_dir.text() or str(default_download_dir()))
        if d:
            self.download_dir.setText(d)

    def load_from_config(self) -> None:
        self.openai_key.setText(self.cfg.openai_api_key)
        self.anthropic_key.setText(self.cfg.anthropic_api_key)
        self.download_dir.setText(self.cfg.download_dir)

    def save(self) -> None:
        self.cfg.openai_api_key = self.openai_key.text().strip()
        self.cfg.anthropic_api_key = self.anthropic_key.text().strip()
        self.cfg.download_dir = self.download_dir.text().strip()
        try:
            save_config(self.cfg)
        except OSError as e:
            self.status.setStyleSheet("color: #c33;")
            self.status.setText(f"保存失败：{e}")
            return
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText("已保存。")
