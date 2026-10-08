"""界面重做的样机（只摆控件，不接功能）：给用户看新版式，定了再真做。

用法：python tools_dev/mock_ui.py 输出文件夹
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ.setdefault("QT_QPA_PLATFORM", "windows")
os.environ["APPDATA"] = tempfile.mkdtemp()
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QCheckBox, QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMainWindow,
    QProgressBar, QPushButton, QSpinBox, QStackedWidget, QTextEdit, QToolButton, QVBoxLayout, QWidget,
)

from app.ui.icons import ICON_PX, gear_icon, globe_icon, palette_icon
from app.ui.theme import apply_theme


def combo(items: list[str], width: int | None = None, current: int = 0) -> QComboBox:
    c = QComboBox()
    c.addItems(items)
    c.setCurrentIndex(current)
    if width:
        c.setFixedWidth(width)
    return c


def label(text: str, role: str = "") -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setObjectName(role)
    return lb


def row(*widgets, stretch_last: bool = False) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setSpacing(8)
    for w in widgets:
        if isinstance(w, int):
            h.addSpacing(w)
        elif w is None:
            h.addStretch(1)
        else:
            h.addWidget(w)
    if stretch_last:
        h.addStretch(1)
    return h


def card(*layouts) -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    v = QVBoxLayout(f)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(10)
    for item in layouts:
        if isinstance(item, QWidget):
            v.addWidget(item)
        else:
            v.addLayout(item)
    return f


def advanced_toggle(text: str) -> QToolButton:
    b = QToolButton()
    b.setText(text)
    b.setCheckable(True)
    b.setArrowType(Qt.ArrowType.RightArrow)
    b.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
    b.setObjectName("advancedToggle")
    return b


def lang_pair() -> QHBoxLayout:
    return row(label("原文"), combo(["自动检测", "日语", "英语", "中文", "韩语"], 110),
               label("→"), combo(["简体中文", "繁体中文", "英语", "日语", "韩语"], 110))


def video_page() -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    v = QVBoxLayout(page)
    v.setContentsMargins(24, 16, 24, 20)
    v.setSpacing(14)

    # 1. 输入：一块大的拖放区
    drop = QFrame()
    drop.setObjectName("dropZone")
    dv = QVBoxLayout(drop)
    dv.setContentsMargins(24, 28, 24, 24)
    dv.setSpacing(10)
    t = label("把视频或音频文件拖到这里")
    t.setObjectName("sectionTitle")
    t.setAlignment(Qt.AlignmentFlag.AlignCenter)
    dv.addWidget(t)
    pick = QPushButton("选择文件…")
    url = QLineEdit()
    url.setPlaceholderText("或粘贴视频网址（YouTube、B 站…）")
    url.setMinimumWidth(360)
    r = row(None, pick, label("或"), url, None)
    dv.addLayout(r)
    v.addWidget(drop)

    # 2. 怎么翻：一行语言对 + 场景 + 风格；一行输出
    opts = card(
        row(*_unpack(lang_pair()), 24, label("场景"), combo(["通用", "游戏 → Valorant", "游戏 → CS2", "电影 → Odyssey", "自动（按内容判断）"], 190),
            16, label("风格"), combo(["字幕", "口语", "半正式", "正式"], 100), None),
        row(label("输出"), QCheckBox("字幕文件 .srt"), QCheckBox("带字幕的视频"), QCheckBox("文档 .txt"),
            24, label("内容"), combo(["原文 + 译文", "仅译文", "仅原文"], 120), 16, QPushButton("字幕样式…"), None),
    )
    opts.layout().itemAt(1).layout().itemAt(1).widget().setChecked(True)
    v.addWidget(opts)

    # 3. 高级（默认收起）
    adv = advanced_toggle("高级：识别 / 翻译模型")
    v.addWidget(adv)
    adv_box = card(
        row(label("识别模型"), combo(["自动（按语言选，推荐）", "gpt-4o-transcribe", "gpt-transcribe", "whisper-1"], 260),
            label("$0.006 / 分钟", "hint"), None),
        row(label("翻译模型"), combo(["Claude", "GPT"], 90), combo(["Sonnet 5.5（推荐）", "Opus 5.5", "Haiku 4.5"], 170),
            label("$2 / $10 每百万字，一小时视频约 3 毛", "hint"), None),
    )
    adv_box.setVisible(False)
    v.addWidget(adv_box)

    # 4. 开始 + 进度
    start = QPushButton("开始处理")
    start.setObjectName("primary")
    start.setMinimumSize(140, 40)
    cancel = QPushButton("取消")
    cancel.setEnabled(False)
    bar = QProgressBar()
    bar.setValue(0)
    status = label("选好文件后点「开始处理」", "hint")
    v.addLayout(row(start, cancel, 12, bar))
    v.addWidget(status)

    # 5. 结果（完成后才出现）
    result = card(
        row(label("完成：43 条字幕 · 费用约 ¥0.4", "statusOk"), None, QPushButton("预览 / 修改字幕"), QPushButton("打开所在文件夹"),
            QPushButton("另存为 SRT…")),
    )
    v.addWidget(result)
    log = QTextEdit()
    log.setPlaceholderText("处理过程中的识别和翻译结果会显示在这里")
    log.setMaximumHeight(110)
    v.addWidget(log)
    v.addStretch(1)
    return page


def realtime_page() -> QWidget:
    page = QWidget()
    page.setObjectName("page")
    v = QVBoxLayout(page)
    v.setContentsMargins(24, 16, 24, 20)
    v.setSpacing(14)

    src = card(
        row(label("听哪里的声音"), combo(["扬声器 (PRO X 2 LIGHTSPEED)（默认）", "耳机 (AirPods)"], 380), QPushButton("刷新"),
            label("和 Windows 右下角选扬声器是同一份列表", "hint"), None),
        row(*_unpack(lang_pair()), 24, label("场景"), combo(["通用", "游戏 → Valorant", "游戏 → CS2", "自动（按内容判断）"], 190),
            16, label("风格"), combo(["口语", "字幕", "半正式", "正式"], 100), None),
        row(label("显示"), combo(["原文 + 译文", "仅译文", "仅原文"], 120), 24, label("延迟"),
            _spin(5, " 秒"), label("越短字幕越快，句子更容易被切断", "hint"), None),
    )
    v.addWidget(src)
    adv = advanced_toggle("高级：识别 / 翻译模型")
    v.addWidget(adv)

    start = QPushButton("● 开始")
    start.setObjectName("primary")
    start.setMinimumSize(140, 40)
    stop = QPushButton("停止")
    stop.setEnabled(False)
    overlay = QPushButton("打开悬浮字幕窗")
    level = QProgressBar()
    level.setFixedWidth(120)
    level.setValue(35)
    v.addLayout(row(start, stop, 12, label("音量"), level, None, overlay))

    stream = QTextEdit()
    stream.setPlaceholderText("开始后，识别到的原文和译文会在这里滚动显示")
    v.addWidget(stream, 1)
    v.addLayout(row(label("已识别 128 句 · 本场费用约 ¥0.9", "hint"), None, QPushButton("保存本场字幕")))
    return page


def _unpack(h: QHBoxLayout):
    items = []
    while h.count():
        it = h.takeAt(0)
        if it.widget():
            items.append(it.widget())
        elif it.spacerItem():
            items.append(None)
    return [x for x in items if x is not None]


def _spin(value: int, suffix: str) -> QSpinBox:
    s = QSpinBox()
    s.setRange(2, 30)
    s.setValue(value)
    s.setSuffix(suffix)
    s.setFixedWidth(80)
    return s


EXTRA_QSS = """
QFrame#card { background: %(card)s; border: 1px solid %(card_border)s; border-radius: 10px; }
QFrame#dropZone { background: %(card)s; border: 2px dashed %(input_border)s; border-radius: 12px; }
QToolButton#advancedToggle { color: %(text_dim)s; padding: 2px 4px; }
"""


def main() -> int:
    out = Path(sys.argv[1])
    app = QApplication(sys.argv)
    from app.ui.theme import PALETTES, build_qss
    for name in ("light", "dark"):
        p = PALETTES[name]
        apply_theme(app, name)
        app.setStyleSheet(build_qss(p) + EXTRA_QSS % p)
        win = QMainWindow()
        central = QWidget()
        central.setObjectName("page")
        root = QVBoxLayout(central)
        root.setContentsMargins(24, 12, 24, 0)
        top = QHBoxLayout()
        group = QButtonGroup(win)
        buttons = []
        for i, text in enumerate(("实时翻译", "视频翻译")):
            b = QPushButton(text)
            b.setObjectName("modeButton")
            b.setCheckable(True)
            group.addButton(b, i)
            buttons.append(b)
            top.addWidget(b)
        top.addStretch(1)
        for icon in (globe_icon(), palette_icon(), gear_icon()):
            tb = QToolButton()
            tb.setIcon(icon)
            tb.setIconSize(tb.iconSize().expandedTo(tb.iconSize()))
            tb.setIconSize(__import__("PySide6.QtCore", fromlist=["QSize"]).QSize(ICON_PX, ICON_PX))
            tb.setAutoRaise(True)
            top.addWidget(tb)
        root.addLayout(top)
        stack = QStackedWidget()
        stack.addWidget(realtime_page())
        stack.addWidget(video_page())
        root.addWidget(stack, 1)
        win.setCentralWidget(central)
        win.resize(1020, 700)
        win.show()
        for i, b in enumerate(buttons):
            b.setChecked(True)
            stack.setCurrentIndex(i)
            app.processEvents()
            win.grab().save(str(out / f"mock_{name}_{'realtime' if i == 0 else 'video'}.png"))
        win.close()
    print("ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
