"""视频翻译：本地视频文件或视频网址 → 整段处理 → 字幕文件。阶段 1 只搭界面。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLineEdit, QProgressBar, QPushButton,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.config import Config, save_config
from app.ui.common import hint, not_implemented
from app.ui.model_panel import ModelLanguagePanel
from app.ui.output_mode import OutputModePicker
from app.ui.scene_picker import ScenePicker

VIDEO_FILTER = "视频 / 音频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.mp3 *.m4a *.wav *.flac);;所有文件 (*)"


class VideoPage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        layout = QVBoxLayout(self)
        layout.addWidget(hint("适用于已经录好的视频：输入本地文件或视频网址，整段处理完后输出字幕文件，可以在这里预览修改。"))

        # ---- 来源 ----
        src_box = QGroupBox("视频来源")
        src_form = QFormLayout(src_box)
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择本地视频或音频文件……")
        self.file_button = QPushButton("选择文件")
        self.file_button.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.file_button)
        src_form.addRow("本地文件", file_row)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("或粘贴视频网址（YouTube、B站等），阶段 4 支持")
        src_form.addRow("视频网址", self.url_edit)
        layout.addWidget(src_box)

        # ---- 语言与模型（两页共用同一份设置）----
        self.model_panel = ModelLanguagePanel(cfg)
        self.model_panel.changed.connect(self._on_model_panel_changed)
        layout.addWidget(self.model_panel)

        # ---- 参数 ----
        box = QGroupBox("参数")
        form = QFormLayout(box)
        self.scene = ScenePicker()
        self.scene.set_current(cfg.last_scene)
        self.scene.changed.connect(self._save_scene)
        self.scene.manage_requested.connect(self.manage_scenes_requested.emit)
        form.addRow("内容场景", self.scene)
        self.output_mode = OutputModePicker(cfg.video_output_mode, cfg.target_language_name())
        self.output_mode.changed.connect(self._save_output_mode)
        form.addRow("输出内容", self.output_mode)
        layout.addWidget(box)

        # ---- 处理 ----
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

        self.model_panel.set_translation_enabled(cfg.video_output_mode != "source_only")

    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择视频或音频文件", "", VIDEO_FILTER)
        if path:
            self.file_edit.setText(path)

    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        self._save()

    def _save_output_mode(self, mode: str) -> None:
        self.cfg.video_output_mode = mode
        self.model_panel.set_translation_enabled(mode != "source_only")
        self._save()

    def _on_model_panel_changed(self) -> None:
        self.output_mode.set_target_name(self.cfg.target_language_name())

    def sync_from_config(self) -> None:
        """另一页改了语言 / 模型后同步过来。"""
        self.model_panel.load_from_config()
        self.output_mode.set_target_name(self.cfg.target_language_name())

    def _save(self) -> None:
        try:
            save_config(self.cfg)
        except OSError:
            pass
