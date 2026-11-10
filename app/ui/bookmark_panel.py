# -*- coding: utf-8 -*-
"""书签侧栏。

与目录、搜索共用右侧栏（QStackedWidget 切换）。存储层在 core/library.py，
这里只负责展示与交互：跳转、编辑备注、删除。

刻意不用「✕」这类生僻字形做按钮（详见 titlebar.py 的注释）。
"""
from bisect import bisect_right

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QFont
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QMenu, QPushButton,
                               QVBoxLayout, QWidget)

PANEL_WIDTH = 320


def _fmt_time(ts: int) -> str:
    import datetime
    try:
        return datetime.datetime.fromtimestamp(int(ts)).strftime("%m-%d %H:%M")
    except (OSError, ValueError, OverflowError):
        return ""


class BookmarkPanel(QWidget):
    sig_jump = Signal(int)        # 字节偏移
    sig_add = Signal()
    sig_edit = Signal(int)        # 书签 id -> 主窗口弹输入框
    sig_delete = Signal(int)      # 书签 id
    sig_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TocPanel")          # 复用同一套样式
        self.setFixedWidth(PANEL_WIDTH)
        self._rows = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head.setObjectName("TocHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 10, 8, 8)
        hl.setSpacing(8)
        title = QLabel("书签")
        title.setObjectName("TocTitle")
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Muted")
        hl.addWidget(title)
        hl.addWidget(self.lbl_count)
        hl.addStretch(1)
        btn_close = QPushButton("×")
        btn_close.setObjectName("TocClose")
        btn_close.setFixedSize(22, 22)
        btn_close.setToolTip("关闭书签（Ctrl+Shift+B）")
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.clicked.connect(self.sig_close)
        hl.addWidget(btn_close)
        root.addWidget(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 2, 12, 10)
        bl.setSpacing(8)

        self.btn_add = QPushButton("在当前位置添加书签（Ctrl+B）")
        self.btn_add.setObjectName("Primary")
        self.btn_add.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_add.clicked.connect(self.sig_add)
        bl.addWidget(self.btn_add)

        self.list = QListWidget()
        self.list.setObjectName("TocList")
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._on_clicked)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._on_menu)
        bl.addWidget(self.list, 1)

        root.addWidget(body, 1)

    # ------------------------------------------------------------ 数据
    def clear(self) -> None:
        self._rows = []
        self.list.clear()
        self.lbl_count.setText("")
        self._placeholder("还没有书签，按 Ctrl+B 在当前页添加")

    def _placeholder(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setForeground(self.palette().placeholderText())
        self.list.addItem(item)

    def set_bookmarks(self, rows) -> None:
        self._rows = list(rows or ())
        self.list.clear()
        if not self._rows:
            self.lbl_count.setText("")
            self._placeholder("还没有书签，按 Ctrl+B 在当前页添加")
            return

        self.lbl_count.setText("%d 个" % len(self._rows))
        base = QFont(self.list.font())
        for r in self._rows:
            excerpt = (r.get("excerpt") or "").strip() or "（无摘要）"
            item = QListWidgetItem(excerpt)
            item.setData(Qt.ItemDataRole.UserRole, int(r["id"]))
            tip = []
            if r.get("chapter_title"):
                tip.append("章节：%s" % r["chapter_title"])
            if r.get("note"):
                tip.append("备注：%s" % r["note"])
            tip.append("位置：%s 字节" % format(int(r.get("offset") or 0), ","))
            if r.get("created_at"):
                tip.append("添加：%s" % _fmt_time(r["created_at"]))
            item.setToolTip("\n".join(tip))
            if r.get("note"):
                f = QFont(base)
                f.setItalic(True)
                item.setFont(f)
            self.list.addItem(item)

    def highlight_offset(self, offset: int) -> None:
        """按阅读位置把最近的书签标亮（不触发跳转）。"""
        if not self._rows:
            return
        offsets = [int(r.get("offset") or 0) for r in self._rows]
        idx = bisect_right(offsets, offset) - 1
        if idx < 0:
            return
        if self.list.currentRow() == idx:
            return
        prev = self.list.blockSignals(True)
        self.list.setCurrentRow(idx)
        self.list.blockSignals(prev)

    def remove_by_id(self, bookmark_id: int) -> None:
        self.set_bookmarks([r for r in self._rows if int(r["id"]) != int(bookmark_id)])

    # ------------------------------------------------------------ 事件
    def _on_clicked(self, item: QListWidgetItem) -> None:
        bid = item.data(Qt.ItemDataRole.UserRole)
        if bid is None:
            return
        for r in self._rows:
            if int(r["id"]) == int(bid):
                self.sig_jump.emit(int(r["offset"]))
                return

    def _on_menu(self, pos) -> None:
        item = self.list.itemAt(pos)
        if item is None:
            return
        bid = item.data(Qt.ItemDataRole.UserRole)
        if bid is None:
            return
        menu = QMenu(self)
        act_jump = QAction("跳转到此处", menu)

        def do_jump():
            for r in self._rows:
                if int(r["id"]) == int(bid):
                    self.sig_jump.emit(int(r["offset"]))

        act_jump.triggered.connect(do_jump)
        menu.addAction(act_jump)

        act_edit = QAction("编辑备注…", menu)
        act_edit.triggered.connect(lambda: self.sig_edit.emit(int(bid)))
        menu.addAction(act_edit)

        menu.addSeparator()
        act_del = QAction("删除书签", menu)
        act_del.triggered.connect(lambda: self.sig_delete.emit(int(bid)))
        menu.addAction(act_del)
        menu.exec(self.list.viewport().mapToGlobal(pos))
