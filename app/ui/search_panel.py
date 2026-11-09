# -*- coding: utf-8 -*-
"""搜索侧栏。

与目录共用右侧栏（QStackedWidget 切换）。搜索是同步执行的：100 MB 文本
实测 35–130 ms，比切线程 + 回传的复杂度更划算；超过 300 ms 才值得上后台线程。
"""
from bisect import bisect_right

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QListWidgetItem, QPushButton,
                               QVBoxLayout, QWidget)

from ..core.search import MAX_HITS, search

PANEL_WIDTH = 320
MAX_SHOWN = 2000          # 列表里最多渲染多少条，再多也是滚不动的
DEBOUNCE_MS = 350


class SearchPanel(QWidget):
    sig_jump = Signal(int, int)      # 命中偏移, 命中长度
    sig_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TocPanel")          # 复用同一套样式
        self.setFixedWidth(PANEL_WIDTH)
        self._tf = None
        self._chapters = []
        self._hits = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        head = QWidget()
        head.setObjectName("TocHeader")
        hl = QHBoxLayout(head)
        hl.setContentsMargins(14, 10, 8, 8)
        hl.setSpacing(8)
        title = QLabel("搜索")
        title.setObjectName("TocTitle")
        hl.addWidget(title)
        hl.addStretch(1)
        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("TocClose")
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setToolTip("关闭搜索（Ctrl+F）")
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.sig_close)
        hl.addWidget(self.btn_close)
        root.addWidget(head)

        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(12, 2, 12, 10)
        bl.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("搜索全文，回车立即定位")
        self.input.setClearButtonEnabled(True)
        self.input.returnPressed.connect(self.run_search)
        self.input.textChanged.connect(self._on_text_changed)
        bl.addWidget(self.input)

        opts = QHBoxLayout()
        opts.setSpacing(10)
        self.chk_case = QCheckBox("区分大小写")
        self.chk_case.stateChanged.connect(self.run_search)
        opts.addWidget(self.chk_case)
        opts.addStretch(1)
        bl.addLayout(opts)

        self.lbl_status = QLabel("输入关键词开始搜索")
        self.lbl_status.setObjectName("Muted")
        bl.addWidget(self.lbl_status)

        self.list = QListWidget()
        self.list.setObjectName("TocList")
        self.list.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(self._on_clicked)
        bl.addWidget(self.list, 1)

        root.addWidget(body, 1)

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(DEBOUNCE_MS)
        self._debounce.timeout.connect(self.run_search)

    # ------------------------------------------------------------ 数据
    def set_target(self, tf, chapters) -> None:
        """绑定当前打开的文档；同一本书只是刷新章节表时不打断已有结果。"""
        if tf is not None and tf is self._tf:
            self._chapters = chapters or self._chapters
            return
        self._tf = tf
        self._chapters = chapters or []
        self._hits = []
        self.list.clear()
        self.input.clear()
        self.lbl_status.setText("输入关键词开始搜索")

    def focus_input(self) -> None:
        self.input.setFocus()
        self.input.selectAll()

    def current_hits(self):
        return self._hits

    def _chapter_of(self, offset: int) -> str:
        if not self._chapters:
            return ""
        offs = [c["start_off"] for c in self._chapters]
        i = bisect_right(offs, offset) - 1
        return self._chapters[i]["title"] if i >= 0 else ""

    # ------------------------------------------------------------ 搜索
    def _on_text_changed(self, _text: str) -> None:
        self._debounce.start()

    def run_search(self) -> None:
        self._debounce.stop()
        if self._tf is None:
            self.lbl_status.setText("先打开一本书")
            return

        kw = self.input.text()
        if not kw.strip():
            self._hits = []
            self.list.clear()
            self.lbl_status.setText("输入关键词开始搜索")
            return

        QGuiApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            hits = search(self._tf, kw, case_sensitive=self.chk_case.isChecked(),
                          limit=MAX_HITS)
        finally:
            QGuiApplication.restoreOverrideCursor()

        self._hits = hits
        self.list.clear()

        if not hits:
            self.lbl_status.setText("没有找到「%s」" % kw)
            return

        capped = len(hits) >= MAX_HITS
        self.lbl_status.setText("找到 %s 条%s" % (
            format(len(hits), ","), "（已达上限，仅显示前 %d 条）" % MAX_HITS if capped else ""))

        for h in hits[:MAX_SHOWN]:
            item = QListWidgetItem(h.excerpt)
            item.setData(Qt.ItemDataRole.UserRole, (h.offset, h.length))
            chap = self._chapter_of(h.offset)
            item.setToolTip("%s\n%s" % (chap, h.excerpt))
            self.list.addItem(item)

    # ------------------------------------------------------------ 事件
    def _on_clicked(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self.sig_jump.emit(int(data[0]), int(data[1]))
