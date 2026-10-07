"""译文风格（语气档位）选择：口语 / 字幕 / 半正式 / 正式。实时页和视频页共用。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from app.config import TONE_NOTES, TONES
from app.ui.common import hint


class TonePicker(QWidget):
    changed = Signal(str)   # casual / subtitle / semiformal / formal

    def __init__(self, current: str = "subtitle", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        for key, label in TONES.items():
            self.combo.addItem(tr(label), key)
        self.combo.setMinimumWidth(120)
        layout.addWidget(self.combo)
        self.note = hint("")
        layout.addWidget(self.note, 1)
        self.set_current(current)
        self.combo.currentIndexChanged.connect(self._on_change)

    def current(self) -> str:
        return self.combo.currentData() or "subtitle"

    def set_current(self, key: str) -> None:
        self.combo.setCurrentIndex(max(0, self.combo.findData(key)))
        self._update_note()

    def _on_change(self) -> None:
        self._update_note()
        self.changed.emit(self.current())

    def _update_note(self) -> None:
        self.note.setText(tr(TONE_NOTES.get(self.current(), "")))
