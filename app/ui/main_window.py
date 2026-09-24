"""主窗口：顶部「实时翻译 / 离线翻译」模式切换 + 右上角齿轮设置。"""
from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QHBoxLayout, QMainWindow, QPushButton, QStackedWidget, QToolButton, QVBoxLayout,
    QWidget,
)

from app.config import Config, save_config
from app.ui.offline_page import OfflinePage
from app.ui.overlay_window import OverlayWindow
from app.ui.realtime_page import RealtimePage
from app.ui.settings_dialog import SettingsDialog

APP_NAME = "字幕翻译器"

MODES = [
    ("realtime", "实时翻译", "直播、在线视频：边看边出字幕"),
    ("offline", "离线翻译", "已录好的视频或网址：整段处理后输出字幕文件"),
]

MODE_BUTTON_STYLE = (
    "QPushButton { font-size: 15px; padding: 8px 22px; border: 1px solid #c8c8c8; background: #fafafa; }"
    "QPushButton:first { border-top-left-radius: 6px; border-bottom-left-radius: 6px; }"
    "QPushButton:checked { background: #2f6fd6; color: white; border-color: #2f6fd6; }"
    "QPushButton:hover:!checked { background: #eef3fb; }"
)


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(APP_NAME)
        self.resize(960, 640)

        self.overlay = OverlayWindow(cfg)
        self.settings_dialog = SettingsDialog(cfg, self)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 10, 14, 10)

        # ---- 顶部：模式切换 + 齿轮 ----
        top = QHBoxLayout()
        self.mode_group = QButtonGroup(self)
        self.mode_group.setExclusive(True)
        self.mode_buttons: dict[str, QPushButton] = {}
        for i, (key, label, tip) in enumerate(MODES):
            b = QPushButton(label)
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setStyleSheet(MODE_BUTTON_STYLE)
            self.mode_group.addButton(b, i)
            self.mode_buttons[key] = b
            top.addWidget(b)
        top.addStretch(1)
        self.settings_button = QToolButton()
        self.settings_button.setText("⚙")
        self.settings_button.setToolTip("设置")
        self.settings_button.setAutoRaise(True)
        self.settings_button.setStyleSheet("QToolButton { font-size: 24px; padding: 2px 8px; }")
        self.settings_button.clicked.connect(lambda: self.settings_dialog.open_tab(SettingsDialog.TAB_BASIC))
        top.addWidget(self.settings_button)
        root.addLayout(top)

        # ---- 页面 ----
        self.stack = QStackedWidget()
        self.realtime_page = RealtimePage(cfg, self.overlay)
        self.offline_page = OfflinePage(cfg)
        self.pages = {"realtime": self.realtime_page, "offline": self.offline_page}
        for key, _, _ in MODES:
            self.stack.addWidget(self.pages[key])
        root.addWidget(self.stack, 1)

        for page in self.pages.values():
            page.manage_scenes_requested.connect(
                lambda: self.settings_dialog.open_tab(SettingsDialog.TAB_SCENES)
            )
        self.mode_group.idClicked.connect(self._on_mode_clicked)

        self.show_mode(cfg.last_mode if cfg.last_mode in self.pages else "realtime")

        if cfg.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(cfg.window_geometry.encode()))

    def _on_mode_clicked(self, index: int) -> None:
        self.show_mode(MODES[index][0])

    def show_mode(self, key: str) -> None:
        self.mode_buttons[key].setChecked(True)
        self.stack.setCurrentWidget(self.pages[key])
        if self.cfg.last_mode != key:
            self.cfg.last_mode = key
            try:
                save_config(self.cfg)
            except OSError:
                pass

    def current_mode(self) -> str:
        for key, page in self.pages.items():
            if self.stack.currentWidget() is page:
                return key
        return ""

    def closeEvent(self, event) -> None:
        self.cfg.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        try:
            save_config(self.cfg)
        except OSError:
            pass
        self.overlay.close()
        self.settings_dialog.close()
        super().closeEvent(event)
