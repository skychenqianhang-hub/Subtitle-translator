"""场景管理页：左侧场景树，右侧编辑术语表等。阶段 1 只搭界面，阶段 3 实现。"""
from __future__ import annotations

from PySide6.QtWidgets import (
    QComboBox, QFormLayout, QHBoxLayout, QLineEdit, QPlainTextEdit, QPushButton, QSplitter,
    QTableWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from app.ui.common import hint, not_implemented, page_title


class ProfilesPage(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.addWidget(page_title("场景管理"))
        layout.addWidget(hint("场景是树状的：子场景自动继承父场景的设置，只需要填写想覆盖或追加的部分。术语表会合并。"))

        splitter = QSplitter()
        layout.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("场景")
        root = QTreeWidgetItem(["通用"])
        game = QTreeWidgetItem(["游戏"])
        game.addChild(QTreeWidgetItem(["CS2"]))
        root.addChild(game)
        self.tree.addTopLevelItem(root)
        self.tree.expandAll()
        self.tree.setCurrentItem(root)
        left_layout.addWidget(self.tree, 1)
        btn_row = QHBoxLayout()
        for text in ("新建子场景", "删除"):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, t=text: not_implemented(self, f"场景「{t}」", "阶段 3"))
            btn_row.addWidget(b)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        right = QWidget()
        form = QFormLayout(right)
        self.asr_model = QComboBox()
        self.asr_model.addItems(["（继承父场景）"])
        self.translate_model = QComboBox()
        self.translate_model.addItems(["（继承父场景）"])
        self.asr_prompt = QLineEdit()
        self.asr_prompt.setPlaceholderText("专有名词提示，逗号分隔，帮助识别听得更准")
        self.corrections = QPlainTextEdit()
        self.corrections.setPlaceholderText("每行一条：听错的词 => 正确写法")
        self.corrections.setMaximumHeight(90)
        self.glossary = QTableWidget(0, 2)
        self.glossary.setHorizontalHeaderLabels(["原文", "译文"])
        self.glossary.horizontalHeader().setStretchLastSection(True)
        self.style = QLineEdit()
        self.style.setPlaceholderText("翻译风格（以后再定）")
        self.style.setEnabled(False)
        form.addRow("识别模型", self.asr_model)
        form.addRow("翻译模型", self.translate_model)
        form.addRow("识别提示词", self.asr_prompt)
        form.addRow("纠错规则", self.corrections)
        form.addRow("术语表", self.glossary)
        form.addRow("翻译风格", self.style)
        io_row = QHBoxLayout()
        for text in ("导入 CSV / Excel", "导出 CSV", "保存"):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, t=text: not_implemented(self, f"术语表「{t}」", "阶段 3"))
            io_row.addWidget(b)
        io_row.addStretch(1)
        form.addRow("", io_row)
        splitter.addWidget(right)
        splitter.setSizes([220, 600])
