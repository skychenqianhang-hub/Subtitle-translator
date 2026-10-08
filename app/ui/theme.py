"""界面主题：一套样式表（QSS）+ 几组配色。启动时 apply_theme(app, 名字)。

配色只改 PALETTES 里的值；控件的形状、间距、圆角写在 build_qss() 里，所有配色共用。
状态文字（成功 / 出错 / 提示）用 objectName 区分：statusOk / statusError / hint，别再手写颜色。
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication

PALETTES: dict[str, dict[str, str]] = {
    # 清爽：浅灰底、白色卡片、蓝色强调
    "light": {
        "window": "#f3f4f6", "card": "#ffffff", "card_border": "#e3e5e8", "input": "#ffffff", "input_border": "#d4d7dc",
        "text": "#1f2328", "text_dim": "#6b7280", "accent": "#2f6fed", "accent_hover": "#255fd1", "accent_text": "#ffffff",
        "accent_soft": "#e8effd", "button": "#ffffff", "button_hover": "#f1f3f6", "button_border": "#cfd3d9",
        "table_header": "#f6f7f9", "grid": "#eceef1", "selection": "#dbe6fb", "ok": "#1a8f4e", "error": "#d03a3a",
        "icon": "#3b3f46", "scrollbar": "#c9ccd2",
    },
    # 深色：直播 / 游戏软件常见的深灰底、紫蓝强调
    "dark": {
        "window": "#17181c", "card": "#1f2126", "card_border": "#2c2f36", "input": "#15161a", "input_border": "#363a43",
        "text": "#e6e7ea", "text_dim": "#9a9fa9", "accent": "#7c6cff", "accent_hover": "#8f82ff", "accent_text": "#ffffff",
        "accent_soft": "#2a2750", "button": "#262930", "button_hover": "#30343c", "button_border": "#3a3e47",
        "table_header": "#24272d", "grid": "#2c2f36", "selection": "#3a3570", "ok": "#4cc38a", "error": "#ff6b6b",
        "icon": "#c9ccd2", "scrollbar": "#3a3e47",
    },
    # 暖调：米白底、青绿强调
    "warm": {
        "window": "#f6f3ee", "card": "#fffdf9", "card_border": "#e6e0d6", "input": "#ffffff", "input_border": "#d9d2c6",
        "text": "#2a2622", "text_dim": "#7a7268", "accent": "#0f8b7a", "accent_hover": "#0c7466", "accent_text": "#ffffff",
        "accent_soft": "#e2f3ef", "button": "#fffdf9", "button_hover": "#f3efe8", "button_border": "#d3cbbf",
        "table_header": "#f5f1ea", "grid": "#ece6dc", "selection": "#d5ece7", "ok": "#1f8a4c", "error": "#c9433a",
        "icon": "#4a443d", "scrollbar": "#cfc7ba",
    },
}
THEME_LABELS = {"light": "清爽蓝", "dark": "深色紫", "warm": "暖调青"}     # 使用处 tr()
DEFAULT_THEME = "light"
_current = DEFAULT_THEME


def current_theme() -> str:
    return _current


def current_palette() -> dict[str, str]:
    return PALETTES.get(_current, PALETTES[DEFAULT_THEME])


def _draw_icon(path: Path, kind: str, color: str, size: int = 24) -> None:
    """kind: down / up / check。画在 24px 画布上，样式表里按 12px 显示，高分屏也清楚。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(color), size / 8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    c = size / 2
    if kind == "down":
        painter.drawPolyline([QPointF(c - 6, c - 3), QPointF(c, c + 3), QPointF(c + 6, c - 3)])
    elif kind == "up":
        painter.drawPolyline([QPointF(c - 6, c + 3), QPointF(c, c - 3), QPointF(c + 6, c + 3)])
    elif kind == "check":
        painter.drawPolyline([QPointF(c - 7, c), QPointF(c - 2, c + 5), QPointF(c + 7, c - 5)])
    painter.end()
    pm.save(str(path), "PNG")


def _icon_urls(p: dict[str, str]) -> dict[str, str]:
    """把当前配色的小图标写到临时目录，返回样式表能用的 url。"""
    folder = Path(tempfile.gettempdir()) / "SubTranslator" / "theme-icons"
    folder.mkdir(parents=True, exist_ok=True)
    urls = {}
    for kind, color in (("down", p["text_dim"]), ("up", p["text_dim"]), ("check", p["accent_text"])):
        f = folder / f"{kind}-{color.lstrip('#')}.png"
        if not f.exists():
            _draw_icon(f, kind, color)
        urls[kind] = f.as_posix()
    return urls


def build_qss(p: dict[str, str]) -> str:
    icon = _icon_urls(p)
    return f"""
QWidget {{
    font-family: "Segoe UI", "Microsoft YaHei UI", "Yu Gothic UI", sans-serif;
    font-size: 10pt;
    color: {p['text']};
}}
QMainWindow, QDialog, QWidget#page {{ background: {p['window']}; }}
QStackedWidget > QWidget {{ background: {p['window']}; }}

/* ---- 卡片（分组框） ---- */
QGroupBox {{
    background: {p['card']};
    border: 1px solid {p['card_border']};
    border-radius: 10px;
    margin-top: 24px;
    padding: 10px 10px 8px 10px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 2px;
    top: 2px;
    padding: 0 4px;
    font-weight: 600;
    color: {p['text_dim']};
}}

/* ---- 按钮 ---- */
QPushButton {{
    background: {p['button']};
    border: 1px solid {p['button_border']};
    border-radius: 6px;
    padding: 6px 14px;
    min-height: 18px;
}}
QPushButton:hover {{ background: {p['button_hover']}; }}
QPushButton:pressed {{ background: {p['accent_soft']}; }}
QPushButton:disabled {{ color: {p['text_dim']}; border-color: {p['card_border']}; background: transparent; }}
QPushButton#primary {{
    background: {p['accent']}; color: {p['accent_text']}; border: 1px solid {p['accent']}; font-weight: 600;
}}
QPushButton#primary:hover {{ background: {p['accent_hover']}; border-color: {p['accent_hover']}; }}
QPushButton#primary:disabled {{ background: {p['button']}; color: {p['text_dim']}; border-color: {p['card_border']}; }}
QPushButton#modeButton {{
    font-size: 11pt; padding: 8px 24px; border-radius: 8px;
    background: transparent; border: 1px solid transparent; color: {p['text_dim']};
}}
QPushButton#modeButton:hover {{ background: {p['button_hover']}; color: {p['text']}; }}
QPushButton#modeButton:checked {{
    background: {p['accent']}; color: {p['accent_text']}; border-color: {p['accent']}; font-weight: 600;
}}
QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 4px 6px; }}
QToolButton:hover {{ background: {p['button_hover']}; }}
QToolButton:pressed {{ background: {p['accent_soft']}; }}

/* ---- 输入框 ---- */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox, QFontComboBox {{
    background: {p['input']};
    border: 1px solid {p['input_border']};
    border-radius: 6px;
    padding: 4px 8px;
    selection-background-color: {p['selection']};
    selection-color: {p['text']};
}}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {p['accent']};
}}
QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QPlainTextEdit:disabled {{
    color: {p['text_dim']}; background: {p['window']};
}}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{icon['down']}"); width: 12px; height: 12px; margin-right: 4px; }}
QComboBox QAbstractItemView {{
    background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 6px;
    selection-background-color: {p['accent_soft']}; selection-color: {p['text']}; padding: 4px; outline: 0;
}}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 18px; border: none; background: transparent; subcontrol-origin: border;
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{icon['up']}"); width: 10px; height: 10px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{icon['down']}"); width: 10px; height: 10px; }}

/* ---- 表格 / 树 ---- */
QTableWidget, QTableView, QTreeWidget, QTreeView, QListWidget {{
    background: {p['input']};
    border: 1px solid {p['card_border']};
    border-radius: 8px;
    gridline-color: {p['grid']};
    selection-background-color: {p['selection']};
    selection-color: {p['text']};
    alternate-background-color: {p['table_header']};
    outline: 0;
}}
QHeaderView::section {{
    background: {p['table_header']};
    color: {p['text_dim']};
    border: none;
    border-bottom: 1px solid {p['card_border']};
    border-right: 1px solid {p['grid']};
    padding: 6px 8px;
    font-weight: 600;
}}
QTableWidget::item, QTreeWidget::item {{ padding: 4px; }}
QTableCornerButton::section {{ background: {p['table_header']}; border: none; }}

/* ---- 标签页 ---- */
QTabWidget::pane {{ border: 1px solid {p['card_border']}; border-radius: 8px; background: {p['card']}; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {p['text_dim']}; padding: 8px 18px; margin-right: 2px;
    border: 1px solid transparent; border-bottom: none; border-top-left-radius: 8px; border-top-right-radius: 8px;
}}
QTabBar::tab:selected {{ background: {p['card']}; color: {p['text']}; border-color: {p['card_border']}; font-weight: 600; }}
QTabBar::tab:hover:!selected {{ color: {p['text']}; }}

/* ---- 勾选 / 单选 ---- */
QCheckBox, QRadioButton {{ spacing: 6px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QCheckBox::indicator {{ border: 1px solid {p['input_border']}; border-radius: 4px; background: {p['input']}; }}
QCheckBox::indicator:checked {{ background: {p['accent']}; border-color: {p['accent']}; image: url("{icon['check']}"); }}
QCheckBox::indicator:disabled {{ border-color: {p['card_border']}; background: {p['window']}; }}
QRadioButton::indicator {{ border: 1px solid {p['input_border']}; border-radius: 8px; background: {p['input']}; }}
QRadioButton::indicator:checked {{ border: 5px solid {p['accent']}; background: {p['input']}; }}

/* ---- 进度条 / 滑块 ---- */
QProgressBar {{
    border: none; border-radius: 5px; background: {p['grid']}; height: 10px; text-align: center; color: transparent;
}}
QProgressBar::chunk {{ background: {p['accent']}; border-radius: 5px; }}
QSlider::groove:horizontal {{ height: 4px; background: {p['grid']}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; background: {p['accent']};
}}
QSlider::sub-page:horizontal {{ background: {p['accent']}; border-radius: 2px; }}

/* ---- 滚动条 ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['scrollbar']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['scrollbar']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ---- 菜单 / 提示 / 分隔 ---- */
QMenu {{ background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 8px; padding: 6px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['accent_soft']}; }}
QToolTip {{ background: {p['card']}; color: {p['text']}; border: 1px solid {p['card_border']}; padding: 4px 8px; }}
QSplitter::handle {{ background: transparent; }}

/* ---- 文字角色 ---- */
QLabel#pageTitle {{ font-size: 16pt; font-weight: 600; margin-bottom: 4px; }}
QLabel#sectionTitle {{ font-size: 12pt; font-weight: 600; }}
QLabel#hint {{ color: {p['text_dim']}; }}
QLabel#statusOk {{ color: {p['ok']}; }}
QLabel#statusError {{ color: {p['error']}; }}
QLabel#statusInfo {{ color: {p['text_dim']}; }}
QLabel#accentText {{ color: {p['accent']}; }}

/* ---- 卡片 / 拖放区 / 折叠按钮 ---- */
QFrame#card {{ background: {p['card']}; border: 1px solid {p['card_border']}; border-radius: 10px; }}
QFrame#card QLabel, QFrame#dropZone QLabel {{ background: transparent; }}
QFrame#dropZone {{ background: {p['card']}; border: 2px dashed {p['input_border']}; border-radius: 12px; }}
QFrame#dropZone[active="true"] {{ border-color: {p['accent']}; background: {p['accent_soft']}; }}
QToolButton#advancedToggle {{ color: {p['text_dim']}; padding: 2px 4px; border: none; }}
QToolButton#advancedToggle:hover {{ color: {p['text']}; background: transparent; }}
"""


def apply_theme(app: QApplication, name: str = DEFAULT_THEME) -> str:
    global _current
    _current = name if name in PALETTES else DEFAULT_THEME
    app.setStyle("Fusion")
    app.setStyleSheet(build_qss(current_palette()))
    return _current
