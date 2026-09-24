"""实时翻译：直播 / 在线视频。抓取某个输出设备的声音，悬浮窗显示字幕。阶段 1 只搭界面。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QPushButton, QSpinBox, QTextEdit, QVBoxLayout,
    QWidget,
)

from app.config import Config, save_config
from app.core.audio_devices import list_output_devices
from app.ui.common import hint, not_implemented
from app.ui.model_panel import ModelLanguagePanel
from app.ui.output_mode import OutputModePicker
from app.ui.overlay_window import OverlayWindow
from app.ui.scene_picker import ScenePicker


class RealtimePage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, overlay: OverlayWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.overlay = overlay
        self._device_connected = False
        layout = QVBoxLayout(self)
        layout.addWidget(hint("适用于直播和在线视频：抓取电脑正在播放的声音，实时识别并翻译，字幕显示在悬浮窗里。任何平台都能用。"))

        # ---- 语言与模型（两页共用同一份设置）----
        self.model_panel = ModelLanguagePanel(cfg)
        self.model_panel.changed.connect(self._on_model_panel_changed)
        layout.addWidget(self.model_panel)

        # ---- 实时参数 ----
        box = QGroupBox("实时参数")
        form = QFormLayout(box)

        self.scene = ScenePicker()
        self.scene.set_current(cfg.last_scene)
        self.scene.changed.connect(self._save_scene)
        self.scene.manage_requested.connect(self.manage_scenes_requested.emit)
        form.addRow("内容场景", self.scene)

        dev_row = QHBoxLayout()
        self.device = QComboBox()
        self.device.setMinimumWidth(320)
        self.refresh_button = QPushButton("刷新")
        self.refresh_button.clicked.connect(self.refresh_devices)
        dev_row.addWidget(self.device, 1)
        dev_row.addWidget(self.refresh_button)
        form.addRow("抓取声音的设备", dev_row)
        form.addRow("", hint("和 Windows 右下角「选择扬声器」是同一份列表。选你正在用来听直播的那个设备。"))

        delay_row = QHBoxLayout()
        self.delay = QSpinBox()
        self.delay.setRange(2, 30)
        self.delay.setSuffix(" 秒")
        self.delay.setValue(cfg.realtime_delay_seconds)
        self.delay.valueChanged.connect(self._save_delay)
        delay_row.addWidget(self.delay)
        delay_row.addWidget(hint("最多攒多长的声音再送去识别。越短字幕越快出，但句子更容易被切断；建议 5 到 8 秒。"), 1)
        form.addRow("翻译延迟", delay_row)

        self.output_mode = OutputModePicker(cfg.realtime_output_mode, cfg.target_language_name())
        self.output_mode.changed.connect(self._save_output_mode)
        form.addRow("输出内容", self.output_mode)
        layout.addWidget(box)

        # ---- 控制 ----
        ctrl_row = QHBoxLayout()
        self.start_button = QPushButton("开始")
        self.start_button.setMinimumHeight(36)
        self.start_button.clicked.connect(lambda: not_implemented(self, "实时字幕", "阶段 5"))
        self.stop_button = QPushButton("停止")
        self.stop_button.setMinimumHeight(36)
        self.stop_button.setEnabled(False)
        self.overlay_button = QPushButton("打开悬浮字幕窗")
        self.overlay_button.setMinimumHeight(36)
        self.overlay_button.clicked.connect(self._toggle_overlay)
        ctrl_row.addWidget(self.start_button)
        ctrl_row.addWidget(self.stop_button)
        ctrl_row.addStretch(1)
        ctrl_row.addWidget(self.overlay_button)
        layout.addLayout(ctrl_row)

        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("开始后，识别到的原文和译文会在这里滚动显示。")
        layout.addWidget(self.log, 1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_button = QPushButton("保存本场字幕")
        self.save_button.clicked.connect(lambda: not_implemented(self, "保存字幕记录", "阶段 5"))
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
            self.device.addItem("电脑正在播放的声音（默认输出设备）", -1)
        else:
            for d in devices:
                label = f"{d.name}（默认）" if d.is_default else d.name
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

    # ---- 悬浮窗 ----
    def _toggle_overlay(self) -> None:
        if self.overlay.isVisible():
            self.overlay.hide()
        else:
            self.overlay.show_demo()

    def _sync_overlay_button(self) -> None:
        self.overlay_button.setText("关闭悬浮字幕窗" if self.overlay.isVisible() else "打开悬浮字幕窗")
