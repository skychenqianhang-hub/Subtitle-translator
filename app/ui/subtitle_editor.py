"""字幕编辑器：像编辑一页幻灯片那样设计字幕。

左边是画面（可播放，作为输出效果预览），字幕块可以直接用鼠标拖到任意位置、滚轮调大小；
右边是样式面板：字体、字号、粗体、颜色、描边、阴影、底框、对齐、精确坐标，译文和原文各一套；
下面是字幕表格，可以改文字、加术语、导出。生成带字幕的视频时完全按这套样式烧录。
"""
from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetricsF, QPainter, QPainterPath, QPen
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDoubleSpinBox, QFileDialog,
    QFontComboBox, QFormLayout, QGraphicsItem, QGraphicsScene, QGraphicsView, QGroupBox, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMainWindow, QMessageBox, QProgressBar, QPushButton, QSlider,
    QSpinBox, QSplitter, QStyle, QTabWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from app.config import OUTPUT_MODES, Config, save_config
from app.core.errors import Cancelled, friendly_message
from app.core.profiles.store import ProfileStore
from app.core.subtitle.ass import wrap_cjk
from app.core.subtitle.burn import burn_subtitles, default_video_path
from app.core.subtitle.document import default_document_path, write_document
from app.core.subtitle.models import SubtitleLine
from app.core.subtitle.project import SubtitleProject
from app.core.subtitle.srt import default_srt_path, fmt_time, write_srt
from app.core.subtitle.style import PLAY_H, PLAY_W, PRESETS, SubtitleStyle, TextStyle, chars_per_line
from app.ui.common import hint

SAMPLE_LINES = [
    SubtitleLine(0.0, 4.0, "This is a sample subtitle line to preview the style.", "这是一条示例字幕，用来预览样式效果。"),
    SubtitleLine(4.0, 8.0, "みなさんこんにちは、今日もよろしくお願いします。", "大家好，今天也请多关照。"),
]


# ====================================================================== 画面上的字幕块（可拖动）
class SubtitleBoxItem(QGraphicsItem):
    """一个字幕块：按 TextStyle 画文字（描边 / 阴影 / 底框），可拖动，滚轮改字号。"""

    def __init__(self, which: str, on_moved, on_resized) -> None:
        super().__init__()
        self.which = which                 # "target" / "source"
        self.sub_style = TextStyle()
        self.text = ""
        self.frame = QRectF(0, 0, 640, 360)   # 实际画面区域（场景坐标）
        self._on_moved = on_moved
        self._on_resized = on_resized
        self._syncing = False
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.setZValue(10)

    # ---------- 几何 ----------
    @property
    def scale_factor(self) -> float:
        return self.frame.height() / PLAY_H if self.frame.height() > 0 else 1.0

    def _font(self) -> QFont:
        f = QFont(self.sub_style.font)
        f.setPixelSize(max(6, int(self.sub_style.size * self.scale_factor)))
        f.setBold(self.sub_style.bold)
        f.setItalic(self.sub_style.italic)
        return f

    def _rows(self) -> list[str]:
        if not self.text:
            return []
        font = self._font()
        fm = QFontMetricsF(font)
        max_w = self.frame.width() * 0.92
        rows: list[str] = []
        for row in wrap_cjk(self.text, chars_per_line(self.sub_style)).split("\\N"):
            while fm.horizontalAdvance(row) > max_w and " " in row:
                cut = row.rfind(" ", 0, max(1, len(row) // 2 + 1))
                if cut <= 0:
                    break
                rows.append(row[:cut])
                row = row[cut + 1:]
            rows.append(row)
        return rows

    def _block_size(self) -> tuple[float, float, float]:
        """(宽, 高, 行高)。"""
        font = self._font()
        fm = QFontMetricsF(font)
        rows = self._rows()
        line_h = fm.ascent() + fm.descent()
        gap = font.pixelSize() * 0.12
        w = max([fm.horizontalAdvance(r) for r in rows] + [font.pixelSize() * 2])
        h = len(rows) * line_h + max(0, len(rows) - 1) * gap
        pad = self._pad()
        return w + 2 * pad, h + 2 * pad, line_h + gap

    def _pad(self) -> float:
        return (max(self.sub_style.outline, 1.0) * 2 + 2) * self.scale_factor

    def sync_from_style(self) -> None:
        """样式里的 x_pct / y_pct → 场景位置。锚点：底边中点 / 左 / 右。"""
        self._syncing = True
        self.prepareGeometryChange()
        w, h, _ = self._block_size()
        ax = self.frame.left() + self.frame.width() * self.sub_style.x_pct / 100
        ay = self.frame.top() + self.frame.height() * self.sub_style.y_pct / 100
        if self.sub_style.align == "left":
            x = ax
        elif self.sub_style.align == "right":
            x = ax - w
        else:
            x = ax - w / 2
        self.setPos(QPointF(x, ay - h))
        self.setVisible(self.sub_style.visible and bool(self.text))
        self._syncing = False
        self.update()

    def _write_back_position(self) -> None:
        w, h, _ = self._block_size()
        p = self.pos()
        if self.sub_style.align == "left":
            ax = p.x()
        elif self.sub_style.align == "right":
            ax = p.x() + w
        else:
            ax = p.x() + w / 2
        ay = p.y() + h
        if self.frame.width() > 0 and self.frame.height() > 0:
            self.sub_style.x_pct = round(max(0.0, min(100.0, (ax - self.frame.left()) / self.frame.width() * 100)), 1)
            self.sub_style.y_pct = round(max(0.0, min(100.0, (ay - self.frame.top()) / self.frame.height() * 100)), 1)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged and not self._syncing:
            self._write_back_position()
            self._on_moved(self.which)
        return super().itemChange(change, value)

    def wheelEvent(self, event) -> None:
        delta = 1 if event.delta() > 0 else -1
        self.sub_style.size = max(6, min(80, self.sub_style.size + delta))
        self._on_resized(self.which)
        event.accept()

    def mousePressEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().mouseReleaseEvent(event)

    # ---------- 绘制 ----------
    def boundingRect(self) -> QRectF:
        w, h, _ = self._block_size()
        return QRectF(-2, -2, w + 4, h + 4)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        st = self.sub_style
        font = self._font()
        fm = QFontMetricsF(font)
        w, h, line_h = self._block_size()
        pad = self._pad()
        s = self.scale_factor
        if st.back_alpha > 0:
            c = QColor(st.back_color)
            c.setAlpha(int(255 * st.back_alpha / 100))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(c)
            painter.drawRoundedRect(QRectF(0, 0, w, h), 3 * s, 3 * s)
        y = pad + fm.ascent()
        for row in self._rows():
            tw = fm.horizontalAdvance(row)
            if st.align == "left":
                x = pad
            elif st.align == "right":
                x = w - pad - tw
            else:
                x = (w - tw) / 2
            path = QPainterPath()
            path.addText(x, y, font, row)
            if st.back_alpha <= 0:
                if st.shadow > 0:
                    painter.save()
                    painter.translate(st.shadow * s, st.shadow * s)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.setBrush(QColor(0, 0, 0, 160))
                    painter.drawPath(path)
                    painter.restore()
                if st.outline > 0:
                    painter.setPen(QPen(QColor(st.outline_color), st.outline * 2 * s, Qt.PenStyle.SolidLine,
                                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawPath(path)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(QColor(st.color)))
            painter.drawPath(path)
            y += line_h
        if self.isSelected():
            painter.setPen(QPen(QColor(80, 160, 255), 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(0, 0, w, h))


class PlayerView(QGraphicsView):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QBrush(QColor(0, 0, 0)))
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.video = QGraphicsVideoItem()
        self.scene().addItem(self.video)
        self.setMinimumHeight(240)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        r = self.viewport().rect()
        self.scene().setSceneRect(0, 0, r.width(), r.height())
        self.video.setSize(r.size().toSizeF())
        self.video.setPos(0, 0)

    def video_rect(self) -> QRectF:
        """实际画面占的区域（视频按比例居中，可能上下或左右留黑边）。没有视频时按 16:9 算。"""
        full = self.scene().sceneRect()
        native = self.video.nativeSize()
        nw, nh = (native.width(), native.height()) if not native.isEmpty() else (16.0, 9.0)
        if full.width() <= 0 or full.height() <= 0:
            return QRectF(0, 0, 640, 360)
        scale = min(full.width() / nw, full.height() / nh)
        w, h = nw * scale, nh * scale
        return QRectF((full.width() - w) / 2, (full.height() - h) / 2, w, h)


# ====================================================================== 样式面板
class StylePanel(QWidget):
    changed = Signal()

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sub_style = TextStyle()
        self._loading = False
        form = QFormLayout(self)
        form.setContentsMargins(6, 6, 6, 6)

        self.visible = QCheckBox(f"显示{title}")
        self.visible.setChecked(True)
        form.addRow(self.visible)

        self.font = QFontComboBox()
        form.addRow("字体", self.font)
        size_row = QHBoxLayout()
        self.size = QSpinBox()
        self.size.setRange(6, 80)
        self.size.setSuffix("")
        size_row.addWidget(self.size)
        self.bold = QCheckBox("粗体")
        self.italic = QCheckBox("斜体")
        size_row.addWidget(self.bold)
        size_row.addWidget(self.italic)
        size_row.addStretch(1)
        form.addRow("字号", size_row)

        self.color = self._color_button()
        form.addRow("文字颜色", self.color)

        ol_row = QHBoxLayout()
        self.outline_color = self._color_button()
        self.outline = QDoubleSpinBox()
        self.outline.setRange(0, 8)
        self.outline.setSingleStep(0.2)
        self.outline.setDecimals(1)
        ol_row.addWidget(self.outline_color)
        ol_row.addWidget(QLabel("粗细"))
        ol_row.addWidget(self.outline)
        form.addRow("描边", ol_row)

        self.shadow = QDoubleSpinBox()
        self.shadow.setRange(0, 8)
        self.shadow.setSingleStep(0.2)
        self.shadow.setDecimals(1)
        form.addRow("阴影", self.shadow)

        bg_row = QHBoxLayout()
        self.back_color = self._color_button()
        self.back_alpha = QSlider(Qt.Orientation.Horizontal)
        self.back_alpha.setRange(0, 100)
        self.back_alpha_label = QLabel("无")
        bg_row.addWidget(self.back_color)
        bg_row.addWidget(QLabel("不透明度"))
        bg_row.addWidget(self.back_alpha, 1)
        bg_row.addWidget(self.back_alpha_label)
        form.addRow("底框", bg_row)

        self.align = QComboBox()
        for key, label in (("left", "左对齐"), ("center", "居中"), ("right", "右对齐")):
            self.align.addItem(label, key)
        form.addRow("对齐", self.align)

        pos_row = QHBoxLayout()
        self.x = QDoubleSpinBox()
        self.x.setRange(0, 100)
        self.x.setDecimals(1)
        self.x.setSuffix(" %")
        self.y = QDoubleSpinBox()
        self.y.setRange(0, 100)
        self.y.setDecimals(1)
        self.y.setSuffix(" %")
        pos_row.addWidget(QLabel("横"))
        pos_row.addWidget(self.x)
        pos_row.addWidget(QLabel("纵"))
        pos_row.addWidget(self.y)
        form.addRow("位置", pos_row)
        form.addRow("", hint("位置也可以直接在画面上拖字幕块；在字幕块上滚动鼠标滚轮可以调字号。"))

        self.visible.toggled.connect(self._emit)
        self.font.currentFontChanged.connect(self._emit)
        self.size.valueChanged.connect(self._emit)
        self.bold.toggled.connect(self._emit)
        self.italic.toggled.connect(self._emit)
        self.outline.valueChanged.connect(self._emit)
        self.shadow.valueChanged.connect(self._emit)
        self.back_alpha.valueChanged.connect(self._emit)
        self.align.currentIndexChanged.connect(self._emit)
        self.x.valueChanged.connect(self._emit)
        self.y.valueChanged.connect(self._emit)

    def _color_button(self) -> QPushButton:
        b = QPushButton()
        b.setFixedSize(60, 24)
        b.clicked.connect(lambda: self._pick_color(b))
        b.setProperty("hex", "#FFFFFF")
        return b

    def _paint_button(self, b: QPushButton, hex_color: str) -> None:
        b.setProperty("hex", hex_color)
        b.setStyleSheet(f"background: {hex_color}; border: 1px solid #888;")
        b.setText("")

    def _pick_color(self, b: QPushButton) -> None:
        c = QColorDialog.getColor(QColor(b.property("hex") or "#FFFFFF"), self, "选择颜色")
        if c.isValid():
            self._paint_button(b, c.name().upper())
            self._emit()

    def load(self, st: TextStyle) -> None:
        self._loading = True
        self.sub_style = st
        self.visible.setChecked(st.visible)
        self.font.setCurrentFont(QFont(st.font))
        self.size.setValue(st.size)
        self.bold.setChecked(st.bold)
        self.italic.setChecked(st.italic)
        self._paint_button(self.color, st.color)
        self._paint_button(self.outline_color, st.outline_color)
        self.outline.setValue(st.outline)
        self.shadow.setValue(st.shadow)
        self._paint_button(self.back_color, st.back_color)
        self.back_alpha.setValue(st.back_alpha)
        self.back_alpha_label.setText("无" if st.back_alpha == 0 else f"{st.back_alpha}%")
        self.align.setCurrentIndex(max(0, self.align.findData(st.align)))
        self.x.setValue(st.x_pct)
        self.y.setValue(st.y_pct)
        self._loading = False

    def _emit(self) -> None:
        if self._loading:
            return
        st = self.sub_style
        st.visible = self.visible.isChecked()
        st.font = self.font.currentFont().family()
        st.size = self.size.value()
        st.bold = self.bold.isChecked()
        st.italic = self.italic.isChecked()
        st.color = self.color.property("hex") or "#FFFFFF"
        st.outline_color = self.outline_color.property("hex") or "#000000"
        st.outline = round(self.outline.value(), 2)
        st.shadow = round(self.shadow.value(), 2)
        st.back_color = self.back_color.property("hex") or "#000000"
        st.back_alpha = self.back_alpha.value()
        self.back_alpha_label.setText("无" if st.back_alpha == 0 else f"{st.back_alpha}%")
        st.align = self.align.currentData() or "center"
        st.x_pct = round(self.x.value(), 1)
        st.y_pct = round(self.y.value(), 1)
        self.changed.emit()


# ====================================================================== 后台烧录
class _BurnWorker(QObject):
    progress = Signal(int)
    finished = Signal(object)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, media: Path, lines: list[SubtitleLine], out: Path, mode: str, style: SubtitleStyle) -> None:
        super().__init__()
        self.media, self.lines, self.out, self.mode, self.sub_style = media, lines, out, mode, style
        self.cancel = threading.Event()

    def run(self) -> None:
        try:
            burn_subtitles(self.media, self.lines, self.out, self.mode, style=self.sub_style,
                           progress=lambda p: self.progress.emit(int(p * 100)), cancel=self.cancel)
            self.finished.emit(self.out)
        except Cancelled:
            self.cancelled.emit()
        except Exception as e:  # noqa: BLE001
            self.failed.emit(friendly_message(e))


# ====================================================================== 编辑器窗口
class SubtitleEditorWindow(QMainWindow):
    COL_START, COL_END, COL_SOURCE, COL_TARGET = 0, 1, 2, 3

    def __init__(self, cfg: Config, store: ProfileStore, project: SubtitleProject,
                 style_only: bool = False, parent: QWidget | None = None) -> None:
        """style_only=True：处理之前预设样式（用示例文字，没有工程文件可保存）。"""
        super().__init__(parent)
        self.cfg = cfg
        self.store = store
        self.project = project
        self.style_only = style_only
        self.lines = project.lines if project.lines else list(SAMPLE_LINES)
        self.sub_style = SubtitleStyle.from_dict(project.style) if project.style else SubtitleStyle.from_dict(cfg.subtitle_style)
        self._dirty = False
        self._loading = False
        self._current_row = -1
        self._burn_thread: QThread | None = None
        self._burn_worker: _BurnWorker | None = None

        media = Path(project.media_path) if project.media_path else None
        self.setWindowTitle(("字幕样式 - " if style_only else "字幕编辑 - ") + (media.name if media else "未选择视频"))
        self.resize(1280, 860)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 8, 10, 8)

        v_split = QSplitter(Qt.Orientation.Vertical)
        root.addWidget(v_split, 1)

        # ================= 上：画面 + 样式面板 =================
        top = QSplitter(Qt.Orientation.Horizontal)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.view = PlayerView()
        left_layout.addWidget(self.view, 1)
        self.box_target = SubtitleBoxItem("target", self._on_box_moved, self._on_box_resized)
        self.box_source = SubtitleBoxItem("source", self._on_box_moved, self._on_box_resized)
        self.view.scene().addItem(self.box_target)
        self.view.scene().addItem(self.box_source)
        self.view.resizeEvent = self._wrap_resize(self.view.resizeEvent)

        self.player = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.view.video)
        self.player.positionChanged.connect(self._on_position)
        self.player.durationChanged.connect(self._on_duration)
        self.player.playbackStateChanged.connect(self._sync_play_button)
        self.player.errorOccurred.connect(self._on_player_error)
        self.view.video.nativeSizeChanged.connect(lambda _: self._refresh_boxes())
        if media and media.exists():
            self.player.setSource(QUrl.fromLocalFile(str(media)))

        ctrl = QHBoxLayout()
        self.play_button = QPushButton()
        self.play_button.setIcon(self.style_icon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_button.setFixedWidth(44)
        self.play_button.setToolTip("播放 / 暂停（预览输出效果）")
        self.play_button.clicked.connect(self.toggle_play)
        ctrl.addWidget(self.play_button)
        self.time_label = QLabel("00:00:00 / 00:00:00")
        self.time_label.setMinimumWidth(150)
        ctrl.addWidget(self.time_label)
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderMoved.connect(lambda v: self.player.setPosition(v))
        self.seek.sliderReleased.connect(lambda: self.player.setPosition(self.seek.value()))
        ctrl.addWidget(self.seek, 1)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(80)
        self.volume.setFixedWidth(90)
        self.volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        self.audio.setVolume(0.8)
        ctrl.addWidget(QLabel("音量"))
        ctrl.addWidget(self.volume)
        left_layout.addLayout(ctrl)

        disp = QHBoxLayout()
        disp.addWidget(QLabel("显示"))
        self.mode = QComboBox()
        for key, label in OUTPUT_MODES.items():
            self.mode.addItem(label.split("（")[0], key)
        self.mode.setCurrentIndex(max(0, self.mode.findData(project.output_mode)))
        self.mode.currentIndexChanged.connect(self._on_mode_changed)
        disp.addWidget(self.mode)
        disp.addSpacing(12)
        disp.addWidget(QLabel("预设"))
        self.preset = QComboBox()
        self.preset.addItem("（选择预设…）", "")
        for name in PRESETS:
            self.preset.addItem(name, name)
        self.preset.currentIndexChanged.connect(self._apply_preset)
        disp.addWidget(self.preset)
        disp.addStretch(1)
        disp.addWidget(hint("在画面上直接拖字幕块、滚轮调字号；右边面板调字体和颜色。"))
        left_layout.addLayout(disp)
        top.addWidget(left)

        # 样式面板
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        self.panel_target = StylePanel("译文")
        self.panel_source = StylePanel("原文")
        self.tabs.addTab(self.panel_target, "译文样式")
        self.tabs.addTab(self.panel_source, "原文样式")
        self.panel_target.changed.connect(lambda: self._on_panel_changed("target"))
        self.panel_source.changed.connect(lambda: self._on_panel_changed("source"))
        right_layout.addWidget(self.tabs, 1)
        self.default_button = QPushButton("设为默认样式（以后的视频都用这套）")
        self.default_button.clicked.connect(self._set_default_style)
        right_layout.addWidget(self.default_button)
        self.style_status = QLabel("")
        self.style_status.setStyleSheet("color: #2a7;")
        right_layout.addWidget(self.style_status)
        top.addWidget(right)
        top.setSizes([860, 380])
        v_split.addWidget(top)

        # ================= 下：表格 + 操作 =================
        bottom = QWidget()
        bottom_layout = QVBoxLayout(bottom)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["开始", "结束", "原文", "译文"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(self.COL_START, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_END, QHeaderView.ResizeMode.ResizeToContents)
        hh.setSectionResizeMode(self.COL_SOURCE, QHeaderView.ResizeMode.Stretch)
        hh.setSectionResizeMode(self.COL_TARGET, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setWordWrap(True)
        self.table.cellChanged.connect(self._on_cell_changed)
        self.table.currentCellChanged.connect(self._on_row_selected)
        bottom_layout.addWidget(self.table, 1)
        bottom_layout.addWidget(hint("单击一行：画面跳到那一句。双击「原文」或「译文」格子：修改文字。" +
                                     ("" if style_only else "改完点右下角「保存修改」。")))

        act = QHBoxLayout()
        self.glossary_button = QPushButton("把这行的词加进术语表…")
        self.glossary_button.clicked.connect(self._add_to_glossary)
        self.correction_button = QPushButton("加进纠错规则…")
        self.correction_button.clicked.connect(self._add_correction)
        act.addWidget(self.glossary_button)
        act.addWidget(self.correction_button)
        act.addSpacing(20)
        self.scene_label = QLabel(f"当前场景：{self.store.display_name(project.scene)}")
        self.scene_label.setStyleSheet("color: #666;")
        act.addWidget(self.scene_label)
        act.addStretch(1)
        self.status = QLabel("")
        self.status.setStyleSheet("color: #2a7;")
        act.addWidget(self.status)
        bottom_layout.addLayout(act)

        out = QHBoxLayout()
        self.export_srt_button = QPushButton("导出 SRT")
        self.export_srt_button.clicked.connect(self._export_srt)
        self.export_doc_button = QPushButton("生成文档")
        self.export_doc_button.clicked.connect(self._export_doc)
        self.burn_button = QPushButton("生成带字幕的视频")
        self.burn_button.clicked.connect(self._burn)
        self.burn_cancel = QPushButton("取消")
        self.burn_cancel.setEnabled(False)
        self.burn_cancel.clicked.connect(self._cancel_burn)
        self.burn_progress = QProgressBar()
        self.burn_progress.setFixedWidth(160)
        self.burn_progress.setVisible(False)
        self.open_folder_button = QPushButton("打开所在文件夹")
        self.open_folder_button.clicked.connect(self._open_folder)
        self.save_button = QPushButton("保存修改")
        self.save_button.setMinimumHeight(32)
        self.save_button.clicked.connect(self.save_project)
        for w in (self.export_srt_button, self.export_doc_button, self.burn_button, self.burn_cancel, self.burn_progress):
            out.addWidget(w)
        out.addStretch(1)
        out.addWidget(self.open_folder_button)
        out.addWidget(self.save_button)
        bottom_layout.addLayout(out)
        v_split.addWidget(bottom)
        v_split.setSizes([560, 300])

        if style_only:
            for w in (self.export_srt_button, self.export_doc_button, self.burn_button, self.glossary_button,
                      self.correction_button, self.save_button):
                w.setEnabled(False)
            self.save_button.setToolTip("处理完视频后才有可保存的字幕")

        self.panel_target.load(self.sub_style.target)
        self.panel_source.load(self.sub_style.source)
        self._fill_table()
        self._current_row = 0 if self.lines else -1
        if self._current_row >= 0:
            self.table.selectRow(0)
        self._refresh_boxes()

    def style_icon(self, sp):
        return self.style().standardIcon(sp)

    def _wrap_resize(self, orig):
        def handler(event):
            orig(event)
            self._refresh_boxes()
        return handler

    # ------------------------------------------------------------ 字幕块 / 样式
    def _refresh_boxes(self) -> None:
        rect = self.view.video_rect()
        ln = self.lines[self._current_row] if 0 <= self._current_row < len(self.lines) else None
        mode = self.current_mode()
        if ln is None:
            t_text, s_text = "", ""
        elif mode == "source_only":
            t_text, s_text = ln.source, ""
        elif mode == "target_only":
            t_text, s_text = (ln.target or ln.source), ""
        else:
            t_text, s_text = (ln.target or ln.source), (ln.source if ln.target else "")
        for box, st, text in ((self.box_target, self.sub_style.target, t_text), (self.box_source, self.sub_style.source, s_text)):
            box.frame = rect
            box.sub_style = st
            box.text = text
            box.sync_from_style()

    def _on_box_moved(self, which: str) -> None:
        panel = self.panel_target if which == "target" else self.panel_source
        panel._loading = True
        panel.x.setValue(panel.sub_style.x_pct)
        panel.y.setValue(panel.sub_style.y_pct)
        panel._loading = False
        self._mark_style_changed()

    def _on_box_resized(self, which: str) -> None:
        panel = self.panel_target if which == "target" else self.panel_source
        panel._loading = True
        panel.size.setValue(panel.sub_style.size)
        panel._loading = False
        self._refresh_boxes()
        self._mark_style_changed()

    def _on_panel_changed(self, which: str) -> None:
        self._refresh_boxes()
        self._mark_style_changed()

    def _mark_style_changed(self) -> None:
        self.project.style = self.sub_style.to_dict()
        self._dirty = True
        self.preset.blockSignals(True)
        self.preset.setCurrentIndex(0)
        self.preset.blockSignals(False)
        self.style_status.setText("样式已修改（生成视频时按当前样式；点上面按钮可设为默认）")

    def _apply_preset(self) -> None:
        name = self.preset.currentData()
        if not name:
            return
        preset = PRESETS[name]
        self.sub_style = SubtitleStyle.from_dict(preset.to_dict())
        self.panel_target.load(self.sub_style.target)
        self.panel_source.load(self.sub_style.source)
        self._refresh_boxes()
        self.project.style = self.sub_style.to_dict()
        self._dirty = True
        self.style_status.setText(f"已套用预设「{name}」")

    def _set_default_style(self) -> None:
        self.cfg.subtitle_style = self.sub_style.to_dict()
        try:
            save_config(self.cfg)
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self.style_status.setText("已设为默认样式，以后处理的视频都用这套。")

    def _on_mode_changed(self) -> None:
        self.project.output_mode = self.current_mode()
        self.cfg.video_output_mode = self.project.output_mode
        try:
            save_config(self.cfg)
        except OSError:
            pass
        self._refresh_boxes()

    def current_mode(self) -> str:
        return self.mode.currentData() or "bilingual"

    # ------------------------------------------------------------ 表格
    def _fill_table(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        for ln in self.lines:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for col, text, editable in (
                (self.COL_START, fmt_time(ln.start), False),
                (self.COL_END, fmt_time(ln.end), False),
                (self.COL_SOURCE, ln.source, True),
                (self.COL_TARGET, ln.target, True),
            ):
                item = QTableWidgetItem(text)
                if not editable:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    item.setForeground(QColor("#777"))
                self.table.setItem(r, col, item)
        self.table.resizeRowsToContents()
        self._loading = False

    def _on_cell_changed(self, row: int, col: int) -> None:
        if self._loading or row >= len(self.lines):
            return
        text = self.table.item(row, col).text().strip()
        if col == self.COL_SOURCE:
            self.lines[row].source = text
        elif col == self.COL_TARGET:
            self.lines[row].target = text
        else:
            return
        self._dirty = True
        self.status.setText("有未保存的修改")
        self.table.resizeRowToContents(row)
        if row == self._current_row:
            self._refresh_boxes()

    def _on_row_selected(self, row: int, _col: int, _prev_row: int, _prev_col: int) -> None:
        if self._loading or row < 0 or row >= len(self.lines):
            return
        self._current_row = row
        self.player.setPosition(int(self.lines[row].start * 1000) + 1)
        self._refresh_boxes()

    # ------------------------------------------------------------ 播放（预览）
    def toggle_play(self) -> None:
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _sync_play_button(self) -> None:
        playing = self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
        icon = QStyle.StandardPixmap.SP_MediaPause if playing else QStyle.StandardPixmap.SP_MediaPlay
        self.play_button.setIcon(self.style_icon(icon))

    def _on_duration(self, ms: int) -> None:
        self.seek.setRange(0, max(0, ms))
        self._update_time_label(self.player.position())

    def _on_position(self, ms: int) -> None:
        if not self.seek.isSliderDown():
            self.seek.setValue(ms)
        self._update_time_label(ms)
        row = self.line_index_at(ms / 1000)
        if row >= 0 and row != self._current_row:
            self._current_row = row
            if row >= 0:
                self._loading = True
                self.table.selectRow(row)
                self.table.scrollToItem(self.table.item(row, self.COL_SOURCE), QAbstractItemView.ScrollHint.PositionAtCenter)
                self._loading = False
            self._refresh_boxes()

    def _update_time_label(self, ms: int) -> None:
        self.time_label.setText(f"{fmt_time(ms / 1000)[:8]} / {fmt_time(self.player.duration() / 1000)[:8]}")

    def _on_player_error(self, _err, text: str) -> None:
        self.status.setStyleSheet("color: #c33;")
        self.status.setText(f"播放器：{text or '无法播放这个文件'}（字幕编辑不受影响）")

    def line_index_at(self, t: float) -> int:
        for i, ln in enumerate(self.lines):
            if ln.start <= t < max(ln.end, ln.start + 0.5):
                return i
        return -1

    # ------------------------------------------------------------ 术语 / 纠错
    def _selected_line(self) -> SubtitleLine | None:
        row = self.table.currentRow()
        if 0 <= row < len(self.lines):
            return self.lines[row]
        QMessageBox.information(self, "先选一行", "请先在表格里点一行字幕。")
        return None

    def _pair_dialog(self, title: str, left_label: str, right_label: str, left: str, right: str,
                     note: str) -> tuple[str, str] | None:
        dlg = QDialog(self)
        dlg.setWindowTitle(title)
        dlg.resize(520, 200)
        form = QFormLayout(dlg)
        a = QLineEdit(left)
        b = QLineEdit(right)
        form.addRow(left_label, a)
        form.addRow(right_label, b)
        form.addRow("", hint(note))
        row = QHBoxLayout()
        row.addStretch(1)
        ok = QPushButton("加入")
        cancel = QPushButton("取消")
        ok.clicked.connect(dlg.accept)
        cancel.clicked.connect(dlg.reject)
        row.addWidget(cancel)
        row.addWidget(ok)
        form.addRow(row)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None
        return a.text().strip(), b.text().strip()

    def _add_to_glossary(self) -> None:
        ln = self._selected_line()
        if ln is None:
            return
        res = self._pair_dialog("加入术语表", "原文", "译文", ln.source, ln.target,
                                f"把两边都改成只剩那个词，然后加入。会存进场景「{self.store.display_name(self.project.scene)}」。")
        if not res or not res[0]:
            return
        p = self.store.get(self.project.scene) or self.store.get("通用")
        p.glossary[res[0]] = res[1]
        self.store.save(p)
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText(f"已加入术语表：{res[0]} → {res[1]}")

    def _add_correction(self) -> None:
        ln = self._selected_line()
        if ln is None:
            return
        res = self._pair_dialog("加入纠错规则", "听错的词", "改成", ln.source, "",
                                f"识别后会自动把左边替换成右边。会存进场景「{self.store.display_name(self.project.scene)}」。")
        if not res or not res[0] or not res[1]:
            return
        p = self.store.get(self.project.scene) or self.store.get("通用")
        p.corrections[res[0]] = res[1]
        self.store.save(p)
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText(f"已加入纠错规则：{res[0]} → {res[1]}")

    # ------------------------------------------------------------ 保存 / 导出
    def save_project(self) -> None:
        if self.style_only:
            return
        self.project.style = self.sub_style.to_dict()
        try:
            p = self.project.save()
        except OSError as e:
            QMessageBox.warning(self, "保存失败", str(e))
            return
        self._dirty = False
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText(f"已保存修改：{p.name}")

    def _export_srt(self) -> None:
        default = default_srt_path(self.project.media_path, self.current_mode(), self.project.target_language)
        path, _ = QFileDialog.getSaveFileName(self, "导出 SRT", str(default), "SRT 字幕 (*.srt)")
        if not path:
            return
        try:
            write_srt(path, self.lines, self.current_mode())
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))
            return
        self.status.setText(f"已导出：{Path(path).name}")

    def _export_doc(self) -> None:
        from app.config import SOURCE_LANGUAGES, TARGET_LANGUAGES
        tgt = TARGET_LANGUAGES.get(self.project.target_language, self.project.target_language)
        default = default_document_path(self.project.media_path, self.current_mode(), tgt)
        path, _ = QFileDialog.getSaveFileName(self, "生成文档", str(default), "文本文档 (*.txt)")
        if not path:
            return
        src = SOURCE_LANGUAGES.get(self.project.source_language, "原文")
        src = "原文" if src == "自动检测" else f"原文（{src}）"
        try:
            write_document(path, self.lines, self.current_mode(), title=Path(self.project.media_path).stem,
                           source_name=src, target_name=f"译文（{tgt}）")
            os.startfile(path)
        except OSError as e:
            QMessageBox.warning(self, "生成失败", str(e))
            return
        self.status.setText(f"已生成文档：{Path(path).name}")

    def _burn(self) -> None:
        media = Path(self.project.media_path)
        if not media.exists():
            QMessageBox.warning(self, "找不到视频", f"原视频不在了：{media}")
            return
        from app.config import TARGET_LANGUAGES
        tgt = TARGET_LANGUAGES.get(self.project.target_language, self.project.target_language)
        out = default_video_path(media, self.current_mode(), tgt)
        self._burn_worker = _BurnWorker(media, list(self.lines), out, self.current_mode(),
                                        SubtitleStyle.from_dict(self.sub_style.to_dict()))
        self._burn_thread = QThread(self)
        self._burn_worker.moveToThread(self._burn_thread)
        self._burn_thread.started.connect(self._burn_worker.run)
        self._burn_worker.progress.connect(self.burn_progress.setValue)
        self._burn_worker.finished.connect(self._on_burn_done)
        self._burn_worker.failed.connect(self._on_burn_failed)
        self._burn_worker.cancelled.connect(lambda: self._on_burn_failed("已取消。"))
        for sig in (self._burn_worker.finished, self._burn_worker.failed, self._burn_worker.cancelled):
            sig.connect(self._burn_thread.quit)
        self._burn_thread.finished.connect(self._burn_cleanup)
        self.burn_button.setEnabled(False)
        self.burn_cancel.setEnabled(True)
        self.burn_progress.setVisible(True)
        self.burn_progress.setValue(0)
        self.status.setStyleSheet("color: #555;")
        self.status.setText("正在按当前样式把字幕烧进视频……")
        self._burn_thread.start()

    def _cancel_burn(self) -> None:
        if self._burn_worker:
            self._burn_worker.cancel.set()

    def _burn_cleanup(self) -> None:
        if self._burn_worker:
            self._burn_worker.deleteLater()
        if self._burn_thread:
            self._burn_thread.deleteLater()
        self._burn_worker = None
        self._burn_thread = None
        self.burn_button.setEnabled(True)
        self.burn_cancel.setEnabled(False)
        self.burn_progress.setVisible(False)

    def _on_burn_done(self, out: Path) -> None:
        self.status.setStyleSheet("color: #2a7;")
        self.status.setText(f"已生成：{out.name}")

    def _on_burn_failed(self, msg: str) -> None:
        self.status.setStyleSheet("color: #c33;")
        self.status.setText(msg)

    def _open_folder(self) -> None:
        if self.project.media_path:
            subprocess.Popen(["explorer", "/select,", str(Path(self.project.media_path))])

    # ------------------------------------------------------------ 关闭
    def closeEvent(self, event) -> None:
        if self._dirty and not self.style_only:
            r = QMessageBox.question(self, "有未保存的修改", "字幕或样式有修改还没保存，要保存吗？",
                                     QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel)
            if r == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if r == QMessageBox.StandardButton.Save:
                self.save_project()
        self.player.stop()
        super().closeEvent(event)
