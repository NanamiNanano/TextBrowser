# -*- coding: utf-8 -*-
"""目录侧栏。

注意：这里刻意用 `×`（U+00D7，Latin-1 区）而不是 `✕`（U+2715）。后者属于生僻
字形，Qt/DirectWrite 为它找字体时会枚举整个字体库——之前标题栏就是踩了这个坑，
首帧多吃 470 MB 内存。
"""
from bisect import bisect_right

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout,
                               QWidget)

PANEL_WIDTH = 290


class TocPanel(QWidget):
    sig_jump = Signal(int)          # 章节起始字节偏移
    sig_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TocPanel")
        self.setFixedWidth(PANEL_WIDTH)
        self._offsets = []
        self._items = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head.setObjectName("TocHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 10, 8, 8)
        hl.setSpacing(8)

        self.lbl_title = QLabel("目录")
        self.lbl_title.setObjectName("TocTitle")
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Muted")
        hl.addWidget(self.lbl_title)
        hl.addWidget(self.lbl_count)
        hl.addStretch(1)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TocClose")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setToolTip("关闭目录（Ctrl+T）")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.sig_close)
        hl.addWidget(self.btn_close)

        root.addWidget(head)

        self.list = QListWidget()
        self.list.setObjectName("TocList")
        self.list.setUniformItemSizes(False)
        self.list.setWordWrap(False)
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._on_clicked)
        root.addWidget(self.list, 1)

    # ------------------------------------------------------------ 数据
    def clear(self) -> None:
        self.list.clear()
        self._offsets = []
        self._items = []
        self.lbl_count.setText("")
        self._placeholder("打开一本书后显示目录")

    def set_loading(self) -> None:
        """识别中的占位，避免用户以为这本书没有目录。"""
        self.list.clear()
        self._offsets = []
        self._items = []
        self.lbl_count.setText("识别中…")
        self._placeholder("正在识别章节，请稍候…")

    def _placeholder(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setForeground(self.palette().placeholderText())
        self.list.addItem(item)

    def set_chapters(self, chapters) -> None:
        self.list.clear()
        self._offsets = []
        self._items = []

        if not chapters:
            self.lbl_count.setText("")
            self._placeholder("未识别到章节")
            return

        self.lbl_count.setText("%d 章" % len(chapters))
        base = QFont(self.list.font())
        bold = QFont(base)
        bold.setBold(True)

        for c in chapters:
            level = int(c.get("level") or 1)
            title = str(c.get("title") or "").strip()
            item = QListWidgetItem(("  " * max(0, level - 1)) + title)
            item.setData(Qt.ItemDataRole.UserRole, int(c["start_off"]))
            item.setToolTip(title)
            if level <= 1:
                item.setFont(bold)
            self.list.addItem(item)
            self._items.append(item)
            self._offsets.append(int(c["start_off"]))

    def highlight_offset(self, offset: int) -> None:
        """按阅读位置选中所在章节，并滚动到可见（不触发跳转信号）。"""
        if not self._offsets:
            return
        idx = bisect_right(self._offsets, offset) - 1
        if idx < 0:
            idx = 0
        if self.list.currentRow() == idx:
            return
        prev = self.list.blockSignals(True)
        self.list.setCurrentRow(idx)
        self.list.scrollToItem(self._items[idx], QListWidget.ScrollHint.PositionAtCenter)
        self.list.blockSignals(prev)

    # ------------------------------------------------------------ 事件
    def _on_clicked(self, item: QListWidgetItem) -> None:
        off = item.data(Qt.ItemDataRole.UserRole)
        if off is not None:
            self.sig_jump.emit(int(off))
