"""设置对话框：右上角齿轮打开。两个标签页：基本设置、场景管理。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtWidgets import QDialog, QTabWidget, QVBoxLayout, QWidget

from app.config import Config
from app.core.profiles.store import ProfileStore
from app.ui.profiles_page import ProfilesPage
from app.ui.settings_page import SettingsPage


class SettingsDialog(QDialog):
    TAB_BASIC = 0
    TAB_SCENES = 1

    def __init__(self, cfg: Config, store: ProfileStore, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("设置"))
        self.resize(960, 720)
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.settings_page = SettingsPage(cfg)
        self.profiles_page = ProfilesPage(store, cfg)
        self.tabs.addTab(self.settings_page, "API Key")
        self.tabs.addTab(self.profiles_page, tr("场景管理"))
        layout.addWidget(self.tabs)

    def open_tab(self, index: int) -> None:
        self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()
        self.activateWindow()
