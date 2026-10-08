"""主窗口：顶部「实时翻译 / 视频翻译」模式切换 + 右上角齿轮设置。"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QByteArray, QProcess, QSize
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QHBoxLayout, QMainWindow, QMenu, QMessageBox, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from app.i18n import LANGUAGES, current_language, tr, tr_in

from app.config import Config, save_config
from app.core.profiles.store import ProfileStore
from app.ui.icons import ICON_PX, gear_icon, globe_icon, palette_icon
from app.ui.theme import THEME_LABELS, apply_theme, current_theme
from app.ui.overlay_window import OverlayWindow
from app.ui.realtime_page import RealtimePage
from app.ui.settings_dialog import SettingsDialog
from app.ui.video_page import VideoPage

APP_NAME = "字幕翻译器"

MODES = [
    ("realtime", "实时翻译", "直播、在线视频：边看边出字幕"),
    ("video", "视频翻译", "已录好的视频或网址：整段处理后输出字幕文件"),
]

MENU_NO_ARROW = "QToolButton::menu-indicator { image: none; }"   # 语言按钮不画下拉小箭头


class MainWindow(QMainWindow):
    def __init__(self, cfg: Config) -> None:
        super().__init__()
        self.cfg = cfg
        self.setWindowTitle(tr(APP_NAME))
        self.resize(1020, 740)

        self.overlay = OverlayWindow(cfg)
        self.store = ProfileStore()
        self.settings_dialog = SettingsDialog(cfg, self.store, self)

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
            b = QPushButton(tr(label))
            b.setCheckable(True)
            b.setToolTip(tr(tip))
            b.setObjectName("modeButton")       # 样式在 theme.py
            self.mode_group.addButton(b, i)
            self.mode_buttons[key] = b
            top.addWidget(b)
        top.addStretch(1)
        # 界面语言：地球图标按钮，点开是各语言自己的名字，不认识当前语言的人也能找到
        self.language_button = QToolButton()
        self.language_button.setObjectName("language_button")
        self.language_button.setIcon(globe_icon())
        self.language_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.language_button.setAutoRaise(True)
        self.language_button.setToolTip("界面语言 / 表示言語 / Interface language")
        self.language_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.language_button.setStyleSheet(MENU_NO_ARROW)
        self.language_menu = QMenu(self.language_button)
        self.language_actions: dict[str, QAction] = {}
        group = QActionGroup(self.language_menu)
        group.setExclusive(True)             # 单选：菜单里显示成圆点，不是勾选框
        for code, name in LANGUAGES.items():
            act = self.language_menu.addAction(name)
            act.setCheckable(True)
            act.setChecked(code == current_language())
            group.addAction(act)
            act.triggered.connect(lambda _=False, c=code: self._on_language_chosen(c))
            self.language_actions[code] = act
        self.language_button.setMenu(self.language_menu)
        top.addWidget(self.language_button)
        # 界面配色：调色盘图标，点开单选菜单，选了立刻生效
        self.theme_button = QToolButton()
        self.theme_button.setObjectName("theme_button")
        self.theme_button.setIcon(palette_icon())
        self.theme_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.theme_button.setAutoRaise(True)
        self.theme_button.setToolTip(tr("界面配色"))
        self.theme_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.theme_button.setStyleSheet(MENU_NO_ARROW)
        self.theme_menu = QMenu(self.theme_button)
        self.theme_actions: dict[str, QAction] = {}
        theme_group = QActionGroup(self.theme_menu)
        theme_group.setExclusive(True)
        for key, label in THEME_LABELS.items():
            act = self.theme_menu.addAction(tr(label))
            act.setCheckable(True)
            act.setChecked(key == current_theme())
            act.triggered.connect(lambda _=False, k=key: self._on_theme_chosen(k))
            theme_group.addAction(act)
            self.theme_actions[key] = act
        self.theme_button.setMenu(self.theme_menu)
        top.addWidget(self.theme_button)
        self.settings_button = QToolButton()
        self.settings_button.setIcon(gear_icon())
        self.settings_button.setIconSize(QSize(ICON_PX, ICON_PX))
        self.settings_button.setToolTip(tr("设置（API Key、场景管理）"))
        self.settings_button.setAutoRaise(True)
        self.settings_button.clicked.connect(lambda: self.settings_dialog.open_tab(SettingsDialog.TAB_BASIC))
        top.addWidget(self.settings_button)
        root.addLayout(top)

        # ---- 页面 ----
        self.stack = QStackedWidget()
        self.realtime_page = RealtimePage(cfg, self.store, self.overlay)
        self.video_page = VideoPage(cfg, self.store)
        self.pages = {"realtime": self.realtime_page, "video": self.video_page}
        for key, _, _ in MODES:
            self.stack.addWidget(self.pages[key])
        root.addWidget(self.stack, 1)

        for page in self.pages.values():
            page.manage_scenes_requested.connect(
                lambda: self.settings_dialog.open_tab(SettingsDialog.TAB_SCENES)
            )
        # 两页共用同一份语言 / 模型设置：一页改了，另一页同步
        self.realtime_page.model_panel.changed.connect(self.video_page.sync_from_config)
        self.video_page.model_panel.changed.connect(self.realtime_page.sync_from_config)
        # 场景管理里改了场景树 → 两页的场景选择器刷新
        self.settings_dialog.profiles_page.profiles_changed.connect(self._on_profiles_changed)
        self.mode_group.idClicked.connect(self._on_mode_clicked)

        self.show_mode(cfg.last_mode if cfg.last_mode in self.pages else "realtime")

        if cfg.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(cfg.window_geometry.encode()))

    # ------------------------------------------------------------ 界面语言
    def _on_language_chosen(self, code: str) -> None:
        for c, act in self.language_actions.items():
            act.setChecked(c == code)
        if code == current_language():
            # 选回了当前正在用的语言：把设置也改回来，免得下次启动变了
            if self.cfg.ui_language != code:
                self.cfg.ui_language = code
                self._save_quietly()
            return
        self.cfg.ui_language = code
        self._save_quietly()
        busy = self.realtime_page.is_running() or self.video_page.is_running()
        title = tr_in(code, "切换界面语言")
        if busy:
            QMessageBox.information(self, title, tr_in(code, "界面语言已保存，下次启动程序时生效。（现在有任务正在运行，没有自动重启。）"))
            return
        answer = QMessageBox.question(self, title, tr_in(code, "界面语言在重启程序后生效。现在重启吗？"))
        if answer == QMessageBox.StandardButton.Yes:
            self.restart_app()

    def _on_theme_chosen(self, name: str) -> None:
        app = QApplication.instance()
        if app is not None:
            name = apply_theme(app, name)
        for k, act in self.theme_actions.items():
            act.setChecked(k == name)
        # 图标颜色跟配色走，重画一遍
        self.language_button.setIcon(globe_icon())
        self.theme_button.setIcon(palette_icon())
        self.settings_button.setIcon(gear_icon())
        self.cfg.ui_theme = name
        self._save_quietly()

    def _save_quietly(self) -> None:
        try:
            save_config(self.cfg)
        except OSError:
            pass

    def restart_app(self) -> None:
        """重新启动自己：打包后是 exe，开发时是 python -m app.main。"""
        if getattr(sys, "frozen", False):
            program, args = sys.executable, sys.argv[1:]
        else:
            program, args = sys.executable, ["-m", "app.main"]
        self.close()
        QProcess.startDetached(program, args, os.getcwd())
        QApplication.quit()

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

    def _on_profiles_changed(self) -> None:
        for page in self.pages.values():
            page.scene.reload(keep=self.cfg.last_scene)

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
