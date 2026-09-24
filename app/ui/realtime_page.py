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
from app.ui.overlay_window import OverlayWindow
from app.ui.scene_picker import ScenePicker


class RealtimePage(QWidget):
    manage_scenes_requested = Signal()

    def __init__(self, cfg: Config, overlay: OverlayWindow, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.cfg = cfg
        self.overlay = overlay
        layout = QVBoxLayout(self)
        layout.addWidget(hint("适用于直播和在线视频：抓取电脑正在播放的声音，实时识别并翻译，字幕显示在悬浮窗里。任何平台都能用。"))

        box = QGroupBox("参数")
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
        layout.addWidget(box)

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
        self.log.setPlaceholderText("开始后，识别到的原文和翻译会在这里滚动显示。")
        layout.addWidget(self.log, 1)

        save_row = QHBoxLayout()
        save_row.addStretch(1)
        self.save_button = QPushButton("保存本场字幕")
        self.save_button.clicked.connect(lambda: not_implemented(self, "保存字幕记录", "阶段 5"))
        save_row.addWidget(self.save_button)
        layout.addLayout(save_row)

        self.overlay.visibility_changed.connect(self._sync_overlay_button)
        self.refresh_devices()

    # ---- 设备 ----
    def refresh_devices(self) -> None:
        self.device.clear()
        devices = list_output_devices()
        if not devices:
            self.device.addItem("电脑正在播放的声音（默认输出设备）", -1)
            return
        for d in devices:
            label = f"{d.name}（默认）" if d.is_default else d.name
            self.device.addItem(label, d.index)
        idx = self.device.findText(self.cfg.audio_device_name)
        self.device.setCurrentIndex(idx if idx >= 0 else 0)
        self.device.currentTextChanged.connect(self._save_device)

    def _save_device(self, name: str) -> None:
        self.cfg.audio_device_name = name
        self._save()

    def _save_delay(self, value: int) -> None:
        self.cfg.realtime_delay_seconds = value
        self._save()

    def _save_scene(self, name: str) -> None:
        self.cfg.last_scene = name
        self._save()

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
