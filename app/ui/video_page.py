"""视频翻译：本地视频文件 → 整段处理 → 字幕文件。"""
from __future__ import annotations

from app.i18n import tr

import threading
from pathlib import Path

from PySide6.QtCore import QObject, Qt, QThread, Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit,
    QMessageBox, QProgressBar, QPushButton, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import OUTPUT_KINDS, Config, save_config
from app.core.download import download_video, looks_like_url
from app.core.errors import Cancelled, friendly_message
from app.core.profiles.detect import SceneDetector
from app.core.profiles.store import AUTO_SCENE, EffectiveProfile, ProfileStore
from app.core.subtitle.style import SubtitleStyle
from app.core.subtitle.burn import burn_subtitles, default_video_path
from app.core.subtitle.document import default_document_path, write_document
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.project import PROJECT_SUFFIX, SubtitleProject, project_path_for
from app.core.subtitle.srt import default_srt_path, fmt_time, write_srt
from app.ui.subtitle_editor import SubtitleEditorWindow
from app.ui.common import Collapsible, card, not_implemented, set_status
from app.ui.model_panel import ModelLanguagePanel
from app.ui.output_mode import OutputModePicker
from app.ui.tone_picker import TonePicker
from app.ui.scene_picker import ScenePicker

VIDEO_FILTER = "视频 / 音频文件 (*.mp4 *.mkv *.mov *.avi *.webm *.flv *.ts *.mp3 *.m4a *.wav *.flac *.aac *.ogg);;所有文件 (*)"


class _Worker(QObject):
    """在后台线程里跑整个流程，用信号把进度送回界面。"""
    progress = Signal(int, str)
    log = Signal(str)
    lines = Signal(object)
    finished = Signal(object, object)   # (list[SubtitleLine], dict 输出文件 {"srt": Path, "video": Path, ...})
    failed = Signal(str)
    cancelled = Signal()
    media_resolved = Signal(object)     # 网址下载完成后告诉界面实际的文件路径

    def __init__(self, cfg: Config, media_path: Path | None, output_mode: str, output_kinds: list[str],
                 subtitle_size: str, profile: EffectiveProfile, url: str = "", store: ProfileStore | None = None,
                 auto_scene: bool = False, tone: str = "subtitle") -> None:
        super().__init__()
        self.cfg = cfg
        self.tone = tone
        self.store = store
        self.auto_scene = auto_scene
        self.url = url
        self.media_path = media_path
        self.output_mode = output_mode
        self.output_kinds = output_kinds
        self.subtitle_size = subtitle_size
        self.profile = profile
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            if self.url:
                self.progress.emit(0, tr("正在下载视频"))
                self.log.emit(tr("下载：{0}", self.url))
                self.media_path = download_video(
                    self.url, self.cfg.effective_download_dir(),
                    progress=lambda p, s: self.progress.emit(int(p * 100), s), cancel=self.cancel,
                )
                self.log.emit(tr("已下载到：{0}", self.media_path))
                self.media_resolved.emit(self.media_path)
            from app.core.asr.registry import create_transcriber
            from app.core.pipeline.video_pipeline import VideoJob, VideoPipeline
            from app.core.translate.registry import create_translator

            prof = self.profile
            transcriber = create_transcriber(self.cfg, model=prof.asr_model, source_language=self.cfg.source_language)
            how = tr("（场景指定）") if prof.asr_model else (tr("（按原文语言自动选择）") if self.cfg.asr_model == "auto" else "")
            self.log.emit(tr("场景：{0}；识别模型：{1}{2}", prof.display_name, transcriber.model, how))
            translator = None
            if self.output_mode != "source_only":
                translator = create_translator(self.cfg, prof.translate_provider, prof.translate_model)
                self.log.emit(tr("翻译模型：{0}", translator.model) + (tr("（场景指定）") if prof.translate_model else ""))
            if prof.glossary or prof.corrections or prof.asr_prompt:
                self.log.emit(tr("术语 {0} 条，纠错 {1} 条，识别提示词 {2} 个", len(prof.glossary), len(prof.corrections), len(prof.asr_prompt)))
            detect = None
            if self.auto_scene and self.store is not None:
                detector = SceneDetector(self.store)
                store = self.store

                def detect(text: str):
                    name = detector.choose(text, "通用")
                    return store.resolve(name)
                self.log.emit(tr("场景：自动（识别完成后按内容判断）"))
            pipeline = VideoPipeline(
                self.cfg, transcriber, translator,
                progress=self.progress.emit, log=self.log.emit,
                on_lines=lambda ls: self.lines.emit(list(ls)), cancel=self.cancel,
                detect_scene=detect,
            )
            job = VideoJob(
                media_path=self.media_path,
                output_mode=self.output_mode,
                source_language=self.cfg.source_language,
                target_language=self.cfg.target_language,
                scene=prof.display_name,
                asr_prompt=", ".join(prof.asr_prompt),
                glossary=prof.glossary_for(self.cfg.source_language, self.cfg.target_language),
                corrections=prof.corrections,
                style=prof.style,
                tone=self.tone,
            )
            result = pipeline.run(job)
            if pipeline.detected_scene is not None:
                prof = pipeline.detected_scene
            self.log.emit(tr("本次费用：") + pipeline.cost.summary())
            outputs: dict[str, Path] = {}
            outputs["cost"] = pipeline.cost.summary()
            if "srt" in self.output_kinds:
                srt = default_srt_path(self.media_path, self.output_mode, self.cfg.target_language)
                write_srt(srt, result, self.output_mode)
                outputs["srt"] = srt
                self.log.emit(tr("已保存字幕文件：{0}", srt.name))
            if "doc" in self.output_kinds:
                from app.config import SOURCE_LANGUAGES
                doc = default_document_path(self.media_path, self.output_mode, self.cfg.target_language_name())
                if self.cfg.source_language == "auto" or self.cfg.source_language not in SOURCE_LANGUAGES:
                    src_name = tr("原文")
                else:
                    src_name = tr("原文（{0}）", tr(SOURCE_LANGUAGES[self.cfg.source_language]))
                write_document(doc, result, self.output_mode, title=self.media_path.stem,
                               source_name=src_name, target_name=tr("译文（{0}）", self.cfg.target_language_name()))
                outputs["doc"] = doc
                self.log.emit(tr("已保存文档：{0}", doc.name))
            if "video" in self.output_kinds:
                out = default_video_path(self.media_path, self.output_mode, self.cfg.target_language_name())
                self.progress.emit(0, tr("正在把字幕烧进视频（时间约为视频时长的一半到一倍）"))
                burn_subtitles(
                    self.media_path, result, out, self.output_mode, self.subtitle_size,
                    progress=lambda p: self.progress.emit(int(p * 100), tr("正在把字幕烧进视频 {0}%", int(p * 100))),
                    cancel=self.cancel, style=SubtitleStyle.from_dict(self.cfg.subtitle_style),
                )
                outputs["video"] = out
                self.log.emit(tr("已保存带字幕的视频：{0}", out.name))
            # 字幕工程：以后可以直接打开修改、重新导出，不用再识别翻译
            project = SubtitleProject(
                media_path=str(self.media_path), lines=result, source_language=self.cfg.source_language,
                target_language=self.cfg.target_language, scene=prof.name, output_mode=self.output_mode,
                subtitle_size=self.subtitle_size, subtitle_margin_pct=self.cfg.video_subtitle_margin_pct,
                asr_model=transcriber.model, translate_model=translator.model if translator else "",
                style=SubtitleStyle.from_dict(self.cfg.subtitle_style).to_dict(),
            )
            try:
                outputs["project"] = project.save()
            except OSError as e:
                self.log.emit(tr("字幕工程保存失败（不影响其他输出）：{0}", e))
            self.finished.emit(result, outputs)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_message(e))


class VideoPage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self._thread: QThread | None = None
        self._worker: _Worker | None = None
        self._lines: list[SubtitleLine] = []
        self._last_media: Path | None = None
        self._saved_path: Path | None = None
        self._project: SubtitleProject | None = None
        self._editor: SubtitleEditorWindow | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 16, 24, 20)
        layout.setSpacing(14)

        # ---- 输入：拖放区 ----
        self.drop_zone = QFrame()
        self.drop_zone.setObjectName("dropZone")
        drop_layout = QVBoxLayout(self.drop_zone)
        drop_layout.setContentsMargins(24, 20, 24, 20)
        drop_layout.setSpacing(10)
        self.drop_title = QLabel(tr("把视频或音频文件拖到这里"))
        self.drop_title.setObjectName("sectionTitle")
        self.drop_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_layout.addWidget(self.drop_title)
        file_row = QHBoxLayout()
        file_row.setSpacing(8)
        self.file_button = QPushButton(tr("选择文件…"))
        self.file_button.clicked.connect(self._choose_file)
        self.file_edit = QLineEdit()
        self.file_edit.setPlaceholderText(tr("还没选文件"))
        self.file_edit.textChanged.connect(self._on_file_text)
        file_row.addWidget(self.file_button)
        file_row.addWidget(self.file_edit, 1)
        drop_layout.addLayout(file_row)
        url_row = QHBoxLayout()
        url_row.setSpacing(8)
        url_row.addWidget(QLabel(tr("或粘贴网址")))
        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText(tr("YouTube、B 站等视频链接，会先下载到「设置 → 网址下载」指定的文件夹"))
        url_row.addWidget(self.url_edit, 1)
        drop_layout.addLayout(url_row)
        layout.addWidget(self.drop_zone)

        # ---- 一张卡片：语言 / 场景 / 风格；输出 ----
        self.model_panel = ModelLanguagePanel(cfg)
        self.model_panel.changed.connect(self._on_model_panel_changed)
        box, card_layout = card()
        self.scene = ScenePicker(store)
        self.scene.set_current(cfg.last_scene)
        self.scene.changed.connect(self._save_scene)
        self.scene.manage_requested.connect(self.manage_scenes_requested.emit)
        self.tone = TonePicker(cfg.video_tone)
        self.tone.changed.connect(self._save_tone)
        self.tone.setEnabled(cfg.video_output_mode != "source_only")
        lang_row = QHBoxLayout()
        lang_row.setSpacing(8)
        lang_row.addWidget(self.model_panel.lang_widget)
        lang_row.addSpacing(24)
        lang_row.addWidget(QLabel(tr("场景")))
        lang_row.addWidget(self.scene)
        lang_row.addSpacing(16)
        lang_row.addWidget(QLabel(tr("风格")))
        lang_row.addWidget(self.tone)
        lang_row.addStretch(1)
        card_layout.addLayout(lang_row)

        kind_row = QHBoxLayout()
        kind_row.setSpacing(8)
        kind_row.addWidget(QLabel(tr("输出")))
        self.kind_checks: dict[str, QCheckBox] = {}
        for key, label in OUTPUT_KINDS.items():
            cb = QCheckBox(tr(label))
            cb.setChecked(key in cfg.video_output_kinds)
            cb.toggled.connect(self._save_output_kind)
            self.kind_checks[key] = cb
            kind_row.addWidget(cb)
        kind_row.addSpacing(24)
        kind_row.addWidget(QLabel(tr("内容")))
        self.output_mode = OutputModePicker(cfg.video_output_mode, cfg.target_language_name())
        self.output_mode.changed.connect(self._save_output_mode)
        kind_row.addWidget(self.output_mode)
        kind_row.addSpacing(16)
        self.style_button = QPushButton(tr("字幕样式…"))
        self.style_button.setToolTip(tr("像编辑幻灯片一样，在画面上设置字幕的字体、大小、颜色、位置"))
        self.style_button.clicked.connect(self._open_style_editor)
        kind_row.addWidget(self.style_button)
        kind_row.addStretch(1)
        card_layout.addLayout(kind_row)
        self.kind_hint = QLabel("")          # 输出形式的说明：只作悬停提示
        self.kind_hint.setVisible(False)
        layout.addWidget(box)
        self._apply_output_kind()

        # ---- 高级：模型 ----
        self.advanced = Collapsible(tr("高级：识别 / 翻译模型"), self.model_panel.advanced_widget)
        layout.addWidget(self.advanced)

        # ---- 处理 ----
        run_row = QHBoxLayout()
        run_row.setSpacing(8)
        self.start_button = QPushButton(tr("开始处理"))
        self.start_button.setObjectName("primary")
        self.start_button.setMinimumSize(140, 40)
        self.start_button.clicked.connect(self._start)
        self.cancel_button = QPushButton(tr("取消"))
        self.cancel_button.setMinimumHeight(40)
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self._cancel)
        run_row.addWidget(self.start_button)
        run_row.addWidget(self.cancel_button)
        run_row.addSpacing(12)
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setFormat("%p%")
        run_row.addWidget(self.progress, 1)
        layout.addLayout(run_row)
        self.status = QLabel(tr("选好文件后点「开始处理」"))
        set_status(self.status, "info")
        layout.addWidget(self.status)

        # ---- 结果 ----
        result_box, result_layout = card()
        export_row = QHBoxLayout()
        export_row.setSpacing(8)
        self.result_label = QLabel("")
        set_status(self.result_label, "ok")
        export_row.addWidget(self.result_label, 1)
        self.open_project_button = QPushButton(tr("打开以前的结果…"))
        self.open_project_button.setToolTip(tr("打开之前处理过的视频的字幕工程文件（.字幕工程.json），继续修改或重新导出"))
        self.open_project_button.clicked.connect(self._open_project)
        export_row.addWidget(self.open_project_button)
        self.edit_button = QPushButton(tr("预览 / 修改字幕"))
        self.edit_button.setEnabled(False)
        self.edit_button.clicked.connect(self._open_editor)
        export_row.addWidget(self.edit_button)
        self.open_folder_button = QPushButton(tr("打开所在文件夹"))
        self.open_folder_button.setEnabled(False)
        self.open_folder_button.clicked.connect(self._open_folder)
        export_row.addWidget(self.open_folder_button)
        self.export_button = QPushButton(tr("另存为 SRT…"))
        self.export_button.setEnabled(False)
        self.export_button.clicked.connect(self._export_as)
        export_row.addWidget(self.export_button)
        result_layout.addLayout(export_row)
        layout.addWidget(result_box)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(tr("处理过程中，识别和翻译的结果会显示在这里。"))
        layout.addWidget(self.preview, 1)

        self.model_panel.set_translation_enabled(cfg.video_output_mode != "source_only")
        self.setAcceptDrops(True)

    # ---------------------------------------------------------------- 拖放
    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._set_drop_active(True)

    def dragLeaveEvent(self, event) -> None:
        self._set_drop_active(False)

    def dropEvent(self, event) -> None:
        self._set_drop_active(False)
        for url in event.mimeData().urls():
            p = url.toLocalFile()
            if p:
                self.file_edit.setText(p)
                break

    def _set_drop_active(self, on: bool) -> None:
        self.drop_zone.setProperty("active", "true" if on else "false")
        self.drop_zone.style().unpolish(self.drop_zone)
        self.drop_zone.style().polish(self.drop_zone)

    def _on_file_text(self, text: str) -> None:
        name = Path(text.strip().strip('"')).name if text.strip() else ""
        self.drop_title.setText(tr("已选：{0}", name) if name else tr("把视频或音频文件拖到这里"))

    # ---------------------------------------------------------------- 处理
    def _choose_file(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, tr("选择视频或音频文件"), "", tr(VIDEO_FILTER))
        if path:
            self.file_edit.setText(path)

    def _start(self) -> None:
        url = self.url_edit.text().strip()
        file_text = self.file_edit.text().strip().strip('"')
        path: Path | None = None
        if file_text:
            path = Path(file_text)
            if not path.is_file():
                QMessageBox.warning(self, tr("找不到文件"), tr("这个文件不存在：{0}", path))
                return
            url = ""
        elif url:
            if not looks_like_url(url):
                QMessageBox.warning(self, tr("网址不对"), tr("请粘贴以 http:// 或 https:// 开头的视频链接。"))
                return
        else:
            QMessageBox.warning(self, tr("没有文件"), tr("请先选择一个本地视频或音频文件，或粘贴视频网址。"))
            return
        mode = self.output_mode.current()
        if not self.selected_kinds():
            QMessageBox.warning(self, tr("没有选输出形式"), tr("请至少勾选一种输出形式：字幕文件、带字幕的视频或文档。"))
            return
        if not self.cfg.has_openai_key():
            QMessageBox.warning(self, tr("缺少 API Key"), tr("还没有填 OpenAI 的 API Key（语音识别需要）。\n请点右上角齿轮，在「API Key」里填写。"))
            return
        if mode != "source_only" and self.cfg.translate_provider == "anthropic" and not self.cfg.has_anthropic_key():
            QMessageBox.warning(self, tr("缺少 API Key"), tr("翻译服务选的是 Claude，但还没有填 Anthropic 的 API Key。\n请点右上角齿轮，在「API Key」里填写，或把翻译服务换成 GPT。"))
            return

        self._lines = []
        self._last_media = path
        self._saved_path = None
        self._project = None
        self.edit_button.setEnabled(False)
        self.preview.clear()
        self.result_label.setText("")
        self.open_folder_button.setEnabled(False)
        self.export_button.setEnabled(False)
        self.progress.setValue(0)
        self._set_running(True)

        self._worker = _Worker(self.cfg, path, mode, self.selected_kinds(),
                               self.cfg.video_subtitle_size, self.store.resolve(self.scene.current_name()), url=url,
                               store=self.store, auto_scene=self.scene.current_name() == AUTO_SCENE,
                               tone=self.tone.current())
        self._worker.media_resolved.connect(self._on_media_resolved)
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

    def _on_media_resolved(self, path: Path) -> None:
        self._last_media = Path(path)
        self.file_edit.setText(str(path))
        self.url_edit.clear()

    def _cancel(self) -> None:
        if self._worker:
            self._worker.cancel.set()
            self.status.setText(tr("正在取消，等当前这一步结束……"))
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
        self.url_edit.setEnabled(not running)
        self.model_panel.setEnabled(not running)
        self.output_mode.setEnabled(not running)
        self.tone.setEnabled(not running and self.output_mode.current() != "source_only")
        for cb in self.kind_checks.values():
            cb.setEnabled(not running)
        self.style_button.setEnabled(not running)
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
        cost = outputs.pop("cost", "")
        names = [p.name for k, p in outputs.items() if k != "project"]
        self._saved_path = outputs.get("video") or outputs.get("srt") or outputs.get("doc") or outputs.get("project")
        set_status(self.result_label, "ok")
        self.result_label.setText(tr("已保存：{0}（{1} 条字幕）", '、'.join(names) or '字幕工程', len(lines)) + (tr("　费用：{0}", cost) if cost else ""))
        self.progress.setValue(100)
        self.status.setText(tr("完成"))
        self.open_folder_button.setEnabled(bool(self._saved_path))
        self.export_button.setEnabled(True)
        doc = outputs.get("doc")
        if doc:
            try:
                import os
                os.startfile(str(doc))   # 用系统默认程序（记事本）打开
            except OSError as e:
                self.preview.append(tr("<span style='color:#c33'>文档已保存，但自动打开失败：{0}</span>", _esc(str(e))))
        proj_path = outputs.get("project")
        if proj_path and self._last_media:
            self._project = SubtitleProject(
                media_path=str(self._last_media), lines=lines, source_language=self.cfg.source_language,
                target_language=self.cfg.target_language, scene=self.scene.current_name(),
                output_mode=self.output_mode.current(), subtitle_size=self.cfg.video_subtitle_size,
                subtitle_margin_pct=self.cfg.video_subtitle_margin_pct,
                style=SubtitleStyle.from_dict(self.cfg.subtitle_style).to_dict(),
            )
            self.edit_button.setEnabled(True)
            if self.cfg.open_editor_after_run:
                self._open_editor()

    def _on_failed(self, message: str) -> None:
        self.status.setText(tr("失败"))
        self.preview.append(tr("<span style='color:#c33'><b>出错：</b>{0}</span>", _esc(message)))
        QMessageBox.critical(self, tr("处理失败"), message)
        if self._lines:
            self.export_button.setEnabled(True)

    def _on_cancelled(self) -> None:
        self.status.setText(tr("已取消"))
        self.preview.append(tr("<span style='color:#888'>已取消。</span>"))
        if self._lines:
            self.export_button.setEnabled(True)

    # ---------------------------------------------------------------- 字幕编辑器
    def _open_editor(self) -> None:
        if self._project is None:
            return
        if self._editor is not None:
            self._editor.close()
        self._editor = SubtitleEditorWindow(self.cfg, self.store, self._project, self)
        self._editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._editor.destroyed.connect(lambda: setattr(self, "_editor", None))
        self._editor.show()

    def _open_style_editor(self) -> None:
        """处理之前预设样式：用当前选的视频做画面（没选就是黑底），示例文字做字幕。"""
        media = self.file_edit.text().strip().strip('"')
        proj = SubtitleProject(media_path=media if media and Path(media).is_file() else "", lines=[],
                               source_language=self.cfg.source_language, target_language=self.cfg.target_language,
                               scene=self.scene.current_name(), output_mode=self.output_mode.current(),
                               style=SubtitleStyle.from_dict(self.cfg.subtitle_style).to_dict())
        if self._editor is not None:
            self._editor.close()
        self._editor = SubtitleEditorWindow(self.cfg, self.store, proj, style_only=True, parent=self)
        self._editor.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._editor.destroyed.connect(lambda: setattr(self, "_editor", None))
        self._editor.show()

    def _open_project(self) -> None:
        start = str(self._last_media.parent) if self._last_media else ""
        path, _ = QFileDialog.getOpenFileName(self, tr("打开字幕工程"), start, tr("字幕工程 (*{0});;所有文件 (*)", PROJECT_SUFFIX))
        if not path:
            return
        try:
            self._project = SubtitleProject.load(path)
        except Exception as e:  # noqa: BLE001
            QMessageBox.warning(self, tr("打开失败"), friendly_message(e))
            return
        self._lines = self._project.lines
        self._last_media = Path(self._project.media_path)
        self._render_preview()
        self.edit_button.setEnabled(True)
        self.export_button.setEnabled(True)
        set_status(self.result_label, "ok")
        self.result_label.setText(tr("已打开：{0}（{1} 条字幕）", Path(path).name, len(self._lines)))
        self._open_editor()

    # ---------------------------------------------------------------- 导出
    def _export_as(self) -> None:
        if not self._lines:
            return
        start_dir = str(self._last_media.with_suffix(".srt")) if self._last_media else ""
        path, _ = QFileDialog.getSaveFileName(self, tr("保存字幕"), start_dir, tr("SRT 字幕 (*.srt)"))
        if not path:
            return
        try:
            write_srt(path, self._lines, self.output_mode.current())
            self._saved_path = Path(path)
            set_status(self.result_label, "ok")
            self.result_label.setText(tr("已保存：{0}", Path(path).name))
            self.open_folder_button.setEnabled(True)
        except OSError as e:
            QMessageBox.critical(self, tr("保存失败"), str(e))

    def _open_folder(self) -> None:
        if self._saved_path:
            import subprocess
            subprocess.Popen(["explorer", "/select,", str(self._saved_path)])

    # ---------------------------------------------------------------- 设置
    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        self._save()

    def _save_tone(self, tone: str) -> None:
        self.cfg.video_tone = tone
        self._save()

    def _save_output_mode(self, mode: str) -> None:
        self.cfg.video_output_mode = mode
        self.model_panel.set_translation_enabled(mode != "source_only")
        self.tone.setEnabled(mode != "source_only")
        if self._lines:
            self._render_preview()
        self._save()

    def selected_kinds(self) -> list[str]:
        return [k for k, cb in self.kind_checks.items() if cb.isChecked()]

    def _save_output_kind(self) -> None:
        self.cfg.video_output_kinds = self.selected_kinds()
        self._apply_output_kind()
        self._save()

    def _apply_output_kind(self) -> None:
        kinds = self.selected_kinds()
        burn = "video" in kinds
        if burn:
            text = tr("字幕烧进画面，发给别人直接能看；字体、大小、颜色、位置在「字幕样式…」里设。")
        elif "doc" in kinds and "srt" not in kinds:
            text = tr("文档里原文一整段、译文一整段，不按句切开。")
        elif kinds:
            text = tr("播放器会自动加载同名 .srt；字幕大小由播放器决定。")
        else:
            text = tr("请至少勾选一种。")
        self.kind_hint.setText(text)
        for cb in self.kind_checks.values():
            cb.setToolTip(text)

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
