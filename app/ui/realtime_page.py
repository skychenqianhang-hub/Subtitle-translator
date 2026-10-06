"""实时翻译：直播 / 在线视频。抓取某个输出设备的声音，实时识别翻译，悬浮窗显示字幕。"""
from __future__ import annotations

from app.i18n import tr

import threading
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QMessageBox, QProgressBar,
    QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget,
)

from app.config import Config, save_config
from app.core.audio_devices import list_output_devices
from app.core.errors import friendly_message
from app.core.pipeline.live_pipeline import LiveCallbacks, LiveOptions, LiveSession
from app.core.profiles.detect import SceneDetector
from app.core.profiles.store import AUTO_SCENE, ProfileStore
from app.core.subtitle.document import write_document
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.srt import fmt_time, write_srt
from app.ui.common import hint


class _Bridge(QObject):
    """把后台线程的回调转成 Qt 信号（自动排队到界面线程）。"""
    status = Signal(str)
    log = Signal(str)
    source = Signal(int, object)
    translated = Signal(int, object)
    error = Signal(str)
    level = Signal(float)
    scene = Signal(str, str)
from app.ui.model_panel import ModelLanguagePanel
from app.ui.output_mode import OutputModePicker
from app.ui.overlay_window import OverlayWindow
from app.ui.scene_picker import ScenePicker


class RealtimePage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, store: ProfileStore, overlay: OverlayWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.overlay = overlay
        self._device_connected = False
        self._session: LiveSession | None = None
        self._bridge = _Bridge()
        self._bridge.status.connect(self._on_status)
        self._bridge.log.connect(self._on_log)
        self._bridge.source.connect(self._on_source)
        self._bridge.translated.connect(self._on_translated)
        self._bridge.error.connect(self._on_error)
        self._bridge.level.connect(self._on_level)
        self._bridge.scene.connect(self._on_scene_changed)
        self._session_lines: list[SubtitleLine] = []
        layout = QVBoxLayout(self)
        layout.addWidget(hint(tr("适用于直播和在线视频：抓取电脑正在播放的声音，实时识别并翻译，字幕显示在悬浮窗里。任何平台都能用。")))

        # ---- 语言与模型（两页共用同一份设置）----
        self.model_panel = ModelLanguagePanel(cfg)
        self.model_panel.changed.connect(self._on_model_panel_changed)
        layout.addWidget(self.model_panel)

        # ---- 实时参数 ----
        box = QGroupBox(tr("实时参数"))
        form = QFormLayout(box)

        self.scene = ScenePicker(store)
        self.scene.set_current(cfg.last_scene)
        self.scene.changed.connect(self._save_scene)
        self.scene.manage_requested.connect(self.manage_scenes_requested.emit)
        form.addRow(tr("内容场景"), self.scene)
        self.scene_now = QLabel("")
        self.scene_now.setStyleSheet("color: #2f6fd6;")
        form.addRow("", self.scene_now)

        dev_row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setObjectName("device_combo")
        self.device.setMinimumWidth(320)
        self.refresh_button = QPushButton(tr("刷新"))
        self.refresh_button.clicked.connect(self.refresh_devices)
        dev_row.addWidget(self.device, 1)
        dev_row.addWidget(self.refresh_button)
        form.addRow(tr("抓取声音的设备"), dev_row)
        form.addRow("", hint(tr("和 Windows 右下角「选择扬声器」是同一份列表。选你正在用来听直播的那个设备。")))

        delay_row = QHBoxLayout()
        self.delay = QSpinBox()
        self.delay.setRange(2, 30)
        self.delay.setSuffix(tr(" 秒"))
        self.delay.setValue(cfg.realtime_delay_seconds)
        self.delay.valueChanged.connect(self._save_delay)
        delay_row.addWidget(self.delay)
        delay_row.addWidget(hint(tr("最多攒多长的声音再送去识别。越短字幕越快出，但句子更容易被切断；建议 5 到 8 秒。")), 1)
        form.addRow(tr("翻译延迟"), delay_row)

        self.output_mode = OutputModePicker(cfg.realtime_output_mode, cfg.target_language_name())
        self.output_mode.changed.connect(self._save_output_mode)
        form.addRow(tr("输出内容"), self.output_mode)
        layout.addWidget(box)

        # ---- 控制 ----
        ctrl_row = QHBoxLayout()
        self.start_button = QPushButton(tr("开始"))
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(self.start_session)
        self.stop_button = QPushButton(tr("停止"))
        self.stop_button.setMinimumHeight(36)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_session)
        self.overlay_button = QPushButton(tr("打开悬浮字幕窗"))
        self.overlay_button.setMinimumHeight(36)
        self.overlay_button.clicked.connect(self._toggle_overlay)
        ctrl_row.addWidget(self.start_button)
        ctrl_row.addWidget(self.stop_button)
        ctrl_row.addSpacing(12)
        self.status_label = QLabel(tr("未开始"))
        self.status_label.setStyleSheet("color: #555;")
        ctrl_row.addWidget(self.status_label)
        self.level = QProgressBar()
        self.level.setRange(0, 100)
        self.level.setTextVisible(False)
        self.level.setFixedWidth(120)
        self.level.setToolTip(tr("抓到的声音大小。开始后如果一直是空的，说明选错了设备"))
        ctrl_row.addWidget(QLabel(tr("音量")))
        ctrl_row.addWidget(self.level)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.overlay_button)
        layout.addLayout(ctrl_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText(tr("开始后，识别到的原文和译文会在这里滚动显示。"))
        layout.addWidget(self.log, 1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_button = QPushButton(tr("保存本场字幕"))
        self.save_button.clicked.connect(self.save_session)
        self.save_button.setEnabled(False)
        save_row.addWidget(self.save_button)
        layout.addLayout(save_row)

        self.overlay.visibility_changed.connect(self._sync_overlay_button)
        self.refresh_devices()
        self._apply_output_mode(cfg.realtime_output_mode)

    # ---- 设备 ----
    def refresh_devices(self) -> None:
        self.device.blockSignals(True)
        self.device.clear()
        devices = list_output_devices()
        if not devices:
            self.device.addItem(tr("电脑正在播放的声音（默认输出设备）"), -1)
        else:
            for d in devices:
                label = tr("{0}（默认）", d.name) if d.is_default else d.name
                self.device.addItem(label, d.index)
            idx = self.device.findText(self.cfg.audio_device_name)
            self.device.setCurrentIndex(idx if idx >= 0 else 0)
        self.device.blockSignals(False)
        if not self._device_connected:
            self.device.currentTextChanged.connect(self._save_device)
            self._device_connected = True

    # ---- 保存 ----
    def _save_device(self, name: str) -> None:
        self.cfg.audio_device_name = name
        self._save()

    def _save_delay(self, value: int) -> None:
        self.cfg.realtime_delay_seconds = value
        self._save()

    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        self._save()

    def _save_output_mode(self, mode: str) -> None:
        self.cfg.realtime_output_mode = mode
        self._apply_output_mode(mode)
        self._save()

    def _apply_output_mode(self, mode: str) -> None:
        self.overlay.set_mode(mode)
        self.model_panel.set_translation_enabled(mode != "source_only")

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

    # ---- 实时会话 ----
    def start_session(self) -> None:
        if self._session is not None:
            return
        mode = self.output_mode.current()
        if not self.cfg.has_openai_key():
            QMessageBox.warning(self, tr("缺少 API Key"), tr("还没有填 OpenAI 的 API Key（语音识别需要）。\n请点右上角齿轮填写。"))
            return
        if mode != "source_only" and self.cfg.translate_provider == "anthropic" and not self.cfg.has_anthropic_key():
            QMessageBox.warning(self, tr("缺少 API Key"), tr("翻译服务选的是 Claude，但还没有填 Anthropic 的 API Key。\n请填写，或把翻译服务换成 GPT。"))
            return
        try:
            from app.core.asr.registry import create_transcriber
            from app.core.translate.registry import create_translator
            auto = self.scene.current_name() == AUTO_SCENE
            prof = self.store.resolve(self.scene.current_name())
            transcriber = create_transcriber(self.cfg, model=prof.asr_model, source_language=self.cfg.source_language)
            translator = None if mode == "source_only" else create_translator(self.cfg, prof.translate_provider, prof.translate_model)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, tr("无法开始"), friendly_message(e))
            return
        opts = LiveOptions(
            device_index=self.device.currentData() if self.device.currentData() not in (None, -1) else None,
            max_segment_seconds=float(self.delay.value()),
            output_mode=mode, source_language=self.cfg.source_language, target_language=self.cfg.target_language,
            asr_prompt=", ".join(prof.asr_prompt), glossary=prof.glossary, corrections=prof.corrections,
            style=prof.style, scene=prof.display_name,
            auto_scene=auto, scene_name=prof.name,
        )
        cbs = LiveCallbacks(
            on_status=self._bridge.status.emit, on_log=self._bridge.log.emit,
            on_source=self._bridge.source.emit, on_translated=self._bridge.translated.emit,
            on_error=self._bridge.error.emit, on_level=self._bridge.level.emit,
            on_scene=self._bridge.scene.emit,
        )
        self._session = self._make_session(transcriber, translator, opts, cbs)
        self.scene_now.setText(tr("当前场景：通用（自动判断中）") if auto else "")
        self._session_lines = []
        self.log.clear()
        try:
            self._session.start()
        except Exception as e:  # noqa: BLE001
            self._session = None
            QMessageBox.critical(self, tr("无法开始"), friendly_message(e))
            return
        self.overlay.set_mode(mode)
        self.overlay.clear_subtitle()
        if not self.overlay.isVisible():
            self.overlay.show_demo()
            self.overlay.clear_subtitle()
        self._set_running(True)

    def _make_session(self, transcriber, translator, opts, cbs) -> LiveSession:
        detector = SceneDetector(self.store) if opts.auto_scene else None
        return LiveSession(self.cfg, transcriber, translator, opts, cbs,
                           scene_detector=detector, scene_resolver=self.store.resolve)

    def _on_scene_changed(self, name: str, display: str) -> None:
        self.scene_now.setText(tr("当前场景：{0}（自动）", display))

    def stop_session(self) -> None:
        if self._session is None:
            return
        self.status_label.setText(tr("正在停止，等最后几句处理完……"))
        self.stop_button.setEnabled(False)
        session = self._session

        def _do_stop():
            session.stop()
            self._bridge.status.emit("__stopped__")

        threading.Thread(target=_do_stop, name="live-stop", daemon=True).start()

    def _set_running(self, running: bool) -> None:
        self.start_button.setEnabled(not running)
        self.stop_button.setEnabled(running)
        self.device.setEnabled(not running)
        self.refresh_button.setEnabled(not running)
        self.delay.setEnabled(not running)
        self.model_panel.setEnabled(not running)
        self.scene.setEnabled(not running)
        self.output_mode.setEnabled(not running)
        if not running:
            self.level.setValue(0)

    def is_running(self) -> bool:
        return self._session is not None

    # ---- 回调（已在界面线程）----
    def _on_status(self, text: str) -> None:
        if text == "__stopped__":
            self._session_lines = list(self._session.lines) if self._session else []
            self._session = None
            self._set_running(False)
            self.status_label.setText(tr("已停止"))
            self.save_button.setEnabled(bool(self._session_lines))
            return
        self.status_label.setText(text)

    def _on_log(self, text: str) -> None:
        self.log.append(f"<span style='color:#888'>{_esc(text)}</span>")

    def _on_source(self, idx: int, line: SubtitleLine) -> None:
        self.overlay.show_pending(line.source)
        self.log.append(f"<span style='color:#888'>[{fmt_time(line.start)[:8]}]</span> {_esc(line.source)}")
        self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _on_translated(self, idx: int, line: SubtitleLine) -> None:
        mode = self.output_mode.current()
        if mode == "source_only":
            self.overlay.show_subtitle("", line.source)
        else:
            self.overlay.show_subtitle(line.target or line.source, line.source if mode == "bilingual" else "")
        if line.target:
            self.log.append(f"&nbsp;&nbsp;&nbsp;&nbsp;<b>{_esc(line.target)}</b>")
            self.log.verticalScrollBar().setValue(self.log.verticalScrollBar().maximum())

    def _on_error(self, text: str) -> None:
        self.log.append(f"<span style='color:#c33'>{_esc(text)}</span>")

    def _on_level(self, v: float) -> None:
        self.level.setValue(int(v * 100))

    # ---- 保存本场 ----
    def save_session(self) -> None:
        lines = self._session_lines or (list(self._session.lines) if self._session else [])
        if not lines:
            QMessageBox.information(self, tr("没有内容"), tr("这场还没有识别到任何字幕。"))
            return
        stamp = datetime.now().strftime("%Y-%m-%d %H%M")
        base = self.cfg.effective_download_dir() / tr("直播记录")
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            base = Path.home()
        default = base / tr("直播字幕 {0}.srt", stamp)
        path, _ = QFileDialog.getSaveFileName(self, tr("保存本场字幕"), str(default), tr("SRT 字幕 (*.srt)"))
        if not path:
            return
        mode = self.output_mode.current()
        try:
            write_srt(path, lines, mode)
            doc = Path(path).with_suffix(".txt")
            write_document(doc, lines, mode, title=tr("直播字幕 {0}", stamp))
        except OSError as e:
            QMessageBox.critical(self, tr("保存失败"), str(e))
            return
        self.log.append(tr("<span style='color:#2a7'>已保存：{0} 和同名 .txt 文档</span>", _esc(path)))

    # ---- 悬浮窗 ----
    def _toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show_demo()

    def _sync_overlay_button(self) -> None:
        self.overlay_button.setText(tr("关闭悬浮字幕窗") if self.overlay.isVisible() else tr("打开悬浮字幕窗"))


def _esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
