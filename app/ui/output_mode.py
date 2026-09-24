"""输出内容选择：原文 + 译文 / 仅译文 / 仅原文（不翻译）。实时页和视频页共用。"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QWidget

from app.config import OUTPUT_MODES
from app.ui.common import hint


class OutputModePicker(QWidget):
    changed = Signal(str)  # "bilingual" / "target_only" / "source_only"

    def __init__(self, current: str = "bilingual", target_name: str = "简体中文",
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._target_name = target_name
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.combo = QComboBox()
        for key, label in OUTPUT_MODES.items():
            self.combo.addItem(label, key)
        self.combo.setMinimumWidth(220)
        layout.addWidget(self.combo)
        self.note = hint("")
        layout.addWidget(self.note, 1)
        self.set_current(current)
        self.combo.currentIndexChanged.connect(self._on_change)
        self._update_note()

    def current(self) -> str:
        return self.combo.currentData() or "bilingual"

    def set_current(self, key: str) -> None:
        idx = self.combo.findData(key)
        self.combo.setCurrentIndex(max(0, idx))
        self._update_note()

    def set_target_name(self, name: str) -> None:
        self._target_name = name
        self._update_note()

    def _on_change(self) -> None:
        self._update_note()
        self.changed.emit(self.current())

    def _update_note(self) -> None:
        t = self._target_name
        notes = {
            "bilingual": f"原文在上，{t}译文在下。",
            "target_only": f"只显示 / 输出{t}译文。",
            "source_only": "跳过翻译这一步，只做语音识别，速度更快、费用更低。",
        }
        self.note.setText(notes.get(self.current(), ""))
