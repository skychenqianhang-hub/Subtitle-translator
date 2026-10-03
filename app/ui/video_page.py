"""视频翻译：本地视频文件 → 整段处理 → 字幕文件。"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import OUTPUT_KINDS, Config, save_config
from app.core.errors import Cancelled, friendly_message
from app.core.subtitle.ass import SIZE_LABELS
from app.core.subtitle.burn import burn_subtitles, default_video_path
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.srt import default_srt_path, fmt_time, write_srt
from app.ui.common import hint, not_implemented
from app.ui.model_panel import ModelLanguagePanel
from app.ui.output_mode import OutputModePicker
from app.ui.scene_picker import ScenePicker

VIDEO_FILTER = "视频 / 音频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.ts *.mp3 *.m4a *.wav *.flac *.aac *.ogg);;所有文件 (*)"


class _Worker(QObject):
    """在后台线程里跑整个流程，用信号把进度送回界面。"""
    progress = Signal(int, str)
    log = Signal(str)
    lines = Signal(object)
    finished = Signal(object, object)   # (list[SubtitleLine], dict 输出文件 {"srt": Path, "video": Path})
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, cfg: Config, media_path: Path, output_mode: str, output_kind: str,
                 subtitle_size: str, scene: str) -> None:
        super().__init__()
        self.cfg = cfg
        self.media_path = media_path
        self.output_mode = output_mode
        self.output_kind = output_kind
        self.subtitle_size = subtitle_size
        self.scene = scene
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            from app.core.asr.registry import create_transcriber
            from app.core.pipeline.video_pipeline import VideoJob, VideoPipeline
            from app.core.translate.registry import create_translator

            transcriber = create_transcriber(self.cfg, source_language=self.cfg.source_language)
            self.log.emit(f"识别模型：{transcriber.model}" + ("（按原文语言自动选择）" if self.cfg.asr_model == "auto" else ""))
            translator = None if self.output_mode == "source_only" else create_translator(self.cfg)
            pipeline = VideoPipeline(
                self.cfg, transcriber, translator,
                progress=self.progress.emit, log=self.log.emit,
                on_lines=lambda ls: self.lines.emit(list(ls)), cancel=self.cancel,
            )
            job = VideoJob(
                media_path=self.media_path,
                output_mode=self.output_mode,
                source_language=self.cfg.source_language,
                target_language=self.cfg.target_language,
                scene=self.scene,
            )
            result = pipeline.run(job)
            outputs: dict[str, Path] = {}
            if self.output_kind in ("srt", "both"):
                srt = default_srt_path(self.media_path, self.output_mode, self.cfg.target_language)
                write_srt(srt, result, self.output_mode)
                outputs["srt"] = srt
                self.log.emit(f"已保存字幕文件：{srt.name}")
            if self.output_kind in ("video", "both"):
                out = default_video_path(self.media_path, self.output_mode, self.cfg.target_language_name())
                self.progress.emit(0, "正在把字幕烧进视频（时间约为视频时长的一半到一倍）")
                burn_subtitles(
                    self.media_path, result, out, self.output_mode, self.subtitle_size,
                    progress=lambda p: self.progress.emit(int(p * 100), f"正在把字幕烧进视频 {int(p * 100)}%"),
                    cancel=self.cancel,
                )
                outputs["video"] = out
                self.log.emit(f"已保存带字幕的视频：{out.name}")
            self.finished.emit(result, outputs)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_message(e))


class VideoPage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._lines: list[SubtitleLine] = []
        self._last_media: Path | None = None
        self._saved_path: Path | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(hint("适用于已经录好的视频：输入本地文件，整段处理完后输出字幕文件（保存在视频旁边、同名 .srt）。"))

        # ---- 来源 ----
        src_box = QGroupBox("视频来源")
        src_form = QFormLayout(src_box)
        file_row = QHBoxLayout()
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText("选择本地视频或音频文件，或把文件拖进这个窗口……")
        self.file_button = QPushButton("选择文件")
        self.file_button.clicked.connect(self._choose_file)
        file_row.addWidget(self.file_edit, 1)
        file_row.addWidget(self.file_button)
        src_form.addRow("本地文件", file_row)
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("或粘贴视频网址（YouTube、B站等），阶段 4 支持")
        src_form.addRow("视频网址", self.url_edit)
        layout.addWidget(src_box)

        # ---- 语言与模型 ----
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
        kind_row = QHBoxLayout()
        self.output_kind = QComboBox()
        for key, label in OUTPUT_KINDS.items():
            self.output_kind.addItem(label, key)
        self.output_kind.setCurrentIndex(max(0, self.output_kind.findData(cfg.video_output_kind)))
        self.output_kind.currentIndexChanged.connect(self._save_output_kind)
        kind_row.addWidget(self.output_kind)
        kind_row.addSpacing(12)
        self.size_label = QLabel("字幕字号")
        kind_row.addWidget(self.size_label)
        self.subtitle_size = QComboBox()
        for key, label in SIZE_LABELS.items():
            self.subtitle_size.addItem(label, key)
        self.subtitle_size.setCurrentIndex(max(0, self.subtitle_size.findData(cfg.video_subtitle_size)))
        self.subtitle_size.currentIndexChanged.connect(self._save_subtitle_size)
        kind_row.addWidget(self.subtitle_size)
        self.kind_hint = hint("")
        kind_row.addWidget(self.kind_hint, 1)
        form.addRow("输出形式", kind_row)
        self.output_mode = OutputModePicker(cfg.video_output_mode, cfg.target_language_name())
        self.output_mode.changed.connect(self._save_output_mode)
        form.addRow("输出内容", self.output_mode)
        layout.addWidget(box)
        self._apply_output_kind()

        # ---- 处理 ----
        run_row = QHBoxLayout()
        self.start_button = QPushButton("开始处理")
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton("取消")
        self.cancel_button.setMinimumHeight(36)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        run_row.addWidget(self.progress, 1)
        layout.addLayout(run_row)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #555;")
        layout.addWidget(self.status)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("处理过程中，识别和翻译的结果会显示在这里。")
        layout.addWidget(self.preview, 1)

        export_row = QHBoxLayout()
        self.result_label = QLabel("")
        self.result_label.setStyleSheet("color: #2a7;")
        export_row.addWidget(self.result_label, 1)
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self._open_folder)
        export_row.addWidget(self.open_folder_button)
        self.export_button = QPushButton("另存为 SRT…")
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_as)
        export_row.addWidget(self.export_button)
        layout.addLayout(export_row)

        self.model_panel.set_translation_enabled(cfg.video_output_mode != "source_only")
        self.setAcceptDrops(True)

    # ---------------------------------------------------------------- 拖放
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self.file_edit.setText(p)
                break

    # ---------------------------------------------------------------- 处理
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "选择视频或音频文件", "", VIDEO_FILTER)
        if path:
            self.file_edit.setText(path)

    def _start(self) -> None:
        if self.url_edit.text().strip() and not self.file_edit.text().strip():
            not_implemented(self, "从网址下载视频", "阶段 4")
            return
        path = Path(self.file_edit.text().strip().strip('"'))
        if not path.is_file():
            QMessageBox.warning(self, "没有文件", "请先选择一个本地视频或音频文件。")
            return
        mode = self.output_mode.current()
        if not self.cfg.has_openai_key():
            QMessageBox.warning(self, "缺少 API Key", "还没有填 OpenAI 的 API Key（语音识别需要）。\n请点右上角齿轮，在「API Key」里填写。")
            return
        if mode != "source_only" and self.cfg.translate_provider == "anthropic" and not self.cfg.has_anthropic_key():
            QMessageBox.warning(self, "缺少 API Key", "翻译服务选的是 Claude，但还没有填 Anthropic 的 API Key。\n请点右上角齿轮，在「API Key」里填写，或把翻译服务换成 GPT。")
            return

        self._lines = []
        self._last_media = path
        self._saved_path = None
        self.preview.clear()
        self.result_label.setText("")
        self.open_folder_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_running(True)

        self._worker = _Worker(self.cfg, path, mode, self.output_kind.currentData(),
                               self.subtitle_size.currentData(), self.scene.current_name())
        self._thread = QThread(self)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_progress)
        self._worker.log.connect(self._on_log)
        self._worker.lines.connect(self._on_lines)
        self._worker.finished.connect(self._on_finished)
        self._worker.failed.connect(self._on_failed)
        self._worker.cancelled.connect(self._on_cancelled)
        for sig in (self._worker.finished, self._worker.failed, self._worker.cancelled):
            sig.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel.set()
            self.status.setText("正在取消，等当前这一步结束……")
            self.cancel_button.setEnabled(False)

    def _cleanup_thread(self) -> None:
        if self._worker:
            self._worker.deleteLater()
        if self._thread:
            self._thread.deleteLater()
        self._worker = None
        self._thread = None
        self._set_running(False)

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.cancel_button.setEnabled(running)
        self.file_button.setEnabled(not running)
        self.file_edit.setEnabled(not running)
        self.model_panel.setEnabled(not running)
        self.output_mode.setEnabled(not running)
        self.output_kind.setEnabled(not running)
        self.subtitle_size.setEnabled(not running and self.output_kind.currentData() != "srt")
        self.scene.setEnabled(not running)

    def is_running(self) -> bool:
        return self._thread is not None

    # ---------------------------------------------------------------- 回调
    def _on_progress(self, pct: int, step: str) -> None:
        self.progress.setValue(pct)
        self.status.setText(step)

    def _on_log(self, text: str) -> None:
        self.preview.append(text)

    def _on_lines(self, lines: list[SubtitleLine]) -> None:
        self._lines = lines
        self._render_preview()

    def _render_preview(self) -> None:
        mode = self.output_mode.current()
        html: list[str] = []
        for ln in self._lines:
            t = f"<span style='color:#888'>{fmt_time(ln.start)}</span> "
            if mode == "target_only":
                t += _esc(ln.target or ln.source)
            elif mode == "source_only":
                t += _esc(ln.source)
            else:
                t += _esc(ln.source)
                if ln.target:
                    t += f"<br>&nbsp;&nbsp;&nbsp;&nbsp;<b>{_esc(ln.target)}</b>"
            html.append(t)
        self.preview.setHtml("<br>".join(html))
        self.preview.verticalScrollBar().setValue(self.preview.verticalScrollBar().maximum())

    def _on_finished(self, lines: list[SubtitleLine], outputs: dict) -> None:
        self._lines = lines
        self._render_preview()
        names = [p.name for p in outputs.values()]
        self._saved_path = outputs.get("video") or outputs.get("srt")
        self.result_label.setStyleSheet("color: #2a7;")
        self.result_label.setText(f"已保存：{'、'.join(names)}（共 {len(lines)} 条字幕）")
        self.progress.setValue(100)
        self.status.setText("完成")
        self.open_folder_button.setEnabled(bool(self._saved_path))
        self.export_button.setEnabled(True)

    def _on_failed(self, message: str) -> None:
        self.status.setText("失败")
        self.preview.append(f"<span style='color:#c33'><b>出错：</b>{_esc(message)}</span>")
        QMessageBox.critical(self, "处理失败", message)
        if self._lines:
            self.export_button.setEnabled(True)

    def _on_cancelled(self) -> None:
        self.status.setText("已取消")
        self.preview.append("<span style='color:#888'>已取消。</span>")
        if self._lines:
            self.export_button.setEnabled(True)

    # ---------------------------------------------------------------- 导出
    def _export_as(self) -> None:
        if not self._lines:
            return
        start_dir = str(self._last_media.with_suffix(".srt")) if self._last_media else ""
        path, _ = QFileDialog.getSaveFileName(self, "保存字幕", start_dir, "SRT 字幕 (*.srt)")
        if not path:
            return
        try:
            write_srt(path, self._lines, self.output_mode.current())
            self._saved_path = Path(path)
            self.result_label.setStyleSheet("color: #2a7;")
            self.result_label.setText(f"已保存：{Path(path).name}")
            self.open_folder_button.setEnabled(True)
        except OSError as e:
            QMessageBox.critical(self, "保存失败", str(e))

    def _open_folder(self) -> None:
        if self._saved_path:
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(self._saved_path)])

    # ---------------------------------------------------------------- 设置
    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        self._save()

    def _save_output_mode(self, mode: str) -> None:
        self.cfg.video_output_mode = mode
        self.model_panel.set_translation_enabled(mode != "source_only")
        if self._lines:
            self._render_preview()
        self._save()

    def _save_output_kind(self) -> None:
        self.cfg.video_output_kind = self.output_kind.currentData()
        self._apply_output_kind()
        self._save()

    def _save_subtitle_size(self) -> None:
        self.cfg.video_subtitle_size = self.subtitle_size.currentData()
        self._save()

    def _apply_output_kind(self) -> None:
        kind = self.output_kind.currentData()
        burn = kind != "srt"
        self.size_label.setEnabled(burn)
        self.subtitle_size.setEnabled(burn)
        self.kind_hint.setText(
            "字幕烧进画面，发给别人直接能看；字号由这里控制。" if burn
            else "播放器会自动加载同名 .srt；字幕大小由播放器决定。"
        )

    def _on_model_panel_changed(self) -> None:
        self.output_mode.set_target_name(self.cfg.target_language_name())

    def sync_from_config(self) -> None:
        self.model_panel.load_from_config()
        self.output_mode.set_target_name(self.cfg.target_language_name())

    def _save(self) -> None:
        try:
            save_config(self.cfg)
        except OSError:
            pass


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
