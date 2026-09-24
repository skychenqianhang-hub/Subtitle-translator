"""悬浮字幕窗：独立、置顶、可拖动、可调字号，可选同时显示原文。"""
from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QHideEvent, QMouseEvent, QShowEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from app.config import Config, save_config


class OverlayWindow(QWidget):
    visibility_changed = Signal()

    def __init__(self, cfg: Config) -> None:
        super().__init__(
            None,
            Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint,
        )
        self.cfg = cfg
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self._drag_offset: QPoint | None = None

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.panel = QWidget()
        self.panel.setObjectName("panel")
        self.panel.setStyleSheet("#panel { background: rgba(0, 0, 0, 170); border-radius: 10px; }")
        root.addWidget(self.panel)
        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(16, 10, 16, 10)

        bar = QHBoxLayout()
        self.smaller = self._bar_button("A-", self._font_smaller)
        self.bigger = self._bar_button("A+", self._font_bigger)
        self.source_toggle = self._bar_button("原文", self._toggle_source)
        self.source_toggle.setCheckable(True)
        self.source_toggle.setChecked(cfg.overlay_show_source)
        self.close_button = self._bar_button("×", self.hide)
        for b in (self.smaller, self.bigger, self.source_toggle):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(self.close_button)
        layout.addLayout(bar)

        self.source_label = QLabel("")
        self.source_label.setWordWrap(True)
        self.source_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.target_label = QLabel("")
        self.target_label.setWordWrap(True)
        self.target_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.source_label)
        layout.addWidget(self.target_label)

        self.resize(900, 140)
        self._apply_font()
        self._apply_source_visibility()

    # ---- 显示 ----
    def show_subtitle(self, target: str, source: str = "") -> None:
        self.target_label.setText(target)
        self.source_label.setText(source)
        if not self.isVisible():
            self.show()

    def show_demo(self) -> None:
        self.show_subtitle("这里会显示翻译后的中文字幕（示例）", "ここに翻訳前の原文が表示されます（例）")
        self._center_bottom()

    def _center_bottom(self) -> None:
        screen = self.screen().availableGeometry() if self.screen() else None
        if screen:
            x = screen.x() + (screen.width() - self.width()) // 2
            y = screen.y() + screen.height() - self.height() - 80
            self.move(x, y)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.visibility_changed.emit()

    def hideEvent(self, event: QHideEvent) -> None:
        super().hideEvent(event)
        self.visibility_changed.emit()

    # ---- 字号 / 原文 ----
    def _apply_font(self) -> None:
        size = self.cfg.overlay_font_size
        self.target_label.setStyleSheet(f"color: white; font-size: {size}px; font-weight: 600;")
        self.source_label.setStyleSheet(f"color: #d0d0d0; font-size: {max(12, int(size * 0.6))}px;")

    def _font_bigger(self) -> None:
        self.cfg.overlay_font_size = min(72, self.cfg.overlay_font_size + 2)
        self._apply_font()
        save_config(self.cfg)

    def _font_smaller(self) -> None:
        self.cfg.overlay_font_size = max(12, self.cfg.overlay_font_size - 2)
        self._apply_font()
        save_config(self.cfg)

    def _toggle_source(self) -> None:
        self.cfg.overlay_show_source = self.source_toggle.isChecked()
        self._apply_source_visibility()
        save_config(self.cfg)

    def _apply_source_visibility(self) -> None:
        self.source_label.setVisible(self.cfg.overlay_show_source)

    def _bar_button(self, text: str, slot) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(22)
        b.setStyleSheet(
            "QPushButton { color: #ddd; background: rgba(255,255,255,40); border: none;"
            " border-radius: 4px; padding: 0 8px; }"
            "QPushButton:hover { background: rgba(255,255,255,80); }"
            "QPushButton:checked { background: rgba(80,160,255,160); }"
        )
        b.clicked.connect(slot)
        return b

    # ---- 拖动 ----
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None
