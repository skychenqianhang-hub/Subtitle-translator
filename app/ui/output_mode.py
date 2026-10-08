"""输出内容选择：原文 + 译文 / 仅译文 / 仅原文（不翻译）。实时页和视频页共用。说明放在鼠标悬停提示里。"""
from __future__ import annotations

from app.i18n import tr

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

from app.config import OUTPUT_MODES


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
            self.combo.addItem(tr(label), key)
        layout.addWidget(self.combo)
        self.note = QLabel("")          # 说明文字：只作悬停提示，不占版面
        self.note.setVisible(False)
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
            "bilingual": tr("原文在上，{0}译文在下。", t),
            "target_only": tr("只显示 / 输出{0}译文。", t),
            "source_only": tr("跳过翻译这一步，只做语音识别，速度更快、费用更低。"),
        }
        text = notes.get(self.current(), "")
        self.note.setText(text)
        self.combo.setToolTip(text)
