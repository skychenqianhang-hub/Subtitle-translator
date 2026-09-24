"""离线翻译：本地视频文件或视频网址 → 生成字幕文件 / 带字幕的视频。阶段 1 只搭界面。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QProgressBar,
    QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import Config, save_config
from app.ui.common import hint, not_implemented
from app.ui.scene_picker import ScenePicker

VIDEO_FILTER = "视频 / 音频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.mp3 *.m4a *.wav *.flac);;所有文件 (*)"


class OfflinePage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.addWidget(hint("适用于已经录好的视频：输入本地文件或视频网址，整段处理完后输出中文字幕文件，可以在这里预览修改。"))

        box = QGroupBox("视频来源与参数")
        form = QFormLayout(box)
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择本地视频或音频文件……")
        self.file_button = QPushButton("选择文件")
        self.file_button.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.file_button)
        form.addRow("本地文件", file_row)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("或粘贴视频网址（YouTube、B站等），阶段 4 支持")
        form.addRow("视频网址", self.url_edit)

        self.scene = ScenePicker()
        self.scene.set_current(cfg.last_scene)
        self.scene.changed.connect(self._save_scene)
        self.scene.manage_requested.connect(self.manage_scenes_requested.emit)
        form.addRow("内容场景", self.scene)

        self.bilingual_check = QCheckBox("双语字幕（中文 + 原文）")
        form.addRow("输出", self.bilingual_check)
        layout.addWidget(box)

        run_row = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(lambda: not_implemented(self, "视频处理", "阶段 2"))
        run_row.addWidget(self.start_button)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        run_row.addWidget(self.progress, 1)
        layout.addLayout(run_row)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("处理完成后，字幕会显示在这里，可以预览和修改。")
        layout.addWidget(self.preview, 1)

        export_row = QHBoxLayout()
        export_row.addStretch(1)
        self.export_button = QPushButton("导出 SRT 字幕")
        self.export_button.clicked.connect(lambda: not_implemented(self, "字幕导出", "阶段 2"))
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择视频或音频文件", "", VIDEO_FILTER)
        if path:
            self.file_edit.setText(path)

    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        try:
            save_config(self.cfg)
        except OSError:
            pass
