# -*- coding: utf-8 -*-
"""书架视图：导入、卡片列表、进度展示、拖放。"""
import os

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QFont, QIcon
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel,
                               QMenu, QMessageBox, QProgressBar, QPushButton,
                               QScrollArea, QSizePolicy, QVBoxLayout, QWidget)

from ..config import SUPPORTED_EXTS
from .theme import cover_pixmap


def _human_size(n: int) -> str:
    if n < 1024:
        return "%d B" % n
    if n < 1024 * 1024:
        return "%.1f KB" % (n / 1024)
    if n < 1024 ** 3:
        return "%.1f MB" % (n / 1048576)
    return "%.2f GB" % (n / 1073741824)


class BookCard(QFrame):
    sig_open = Signal(int)
    sig_remove = Signal(int)

    def __init__(self, book: dict, parent=None):
        super().__init__(parent)
        self.book = book
        self.setObjectName("BookCard")
        self.setFixedHeight(96)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QFrame#BookCard { border-radius: 10px; }"
                           "QFrame#BookCard:hover { background: rgba(120,120,120,0.10); }")

        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(12)

        cover = QLabel()
        cover.setFixedSize(56, 76)
        cover.setPixmap(cover_pixmap(book.get("title", ""), 56, 76))
        lay.addWidget(cover)

        right = QVBoxLayout()
        right.setSpacing(3)
        right.setContentsMargins(0, 0, 0, 0)

        title = QLabel(book.get("title") or "未命名")
        title.setObjectName("BookCardTitle")
        title.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        right.addWidget(title)

        fmt = (book.get("format") or "txt").upper()
        enc = book.get("encoding") or ""
        size = _human_size(book.get("file_size") or 0)
        meta_bits = [fmt, size]
        if enc:
            meta_bits.append(enc)
        if not book.get("exists", True):
            meta_bits.append("⚠ 文件缺失")
        meta = QLabel("  ·  ".join(meta_bits))
        meta.setObjectName("Muted")
        right.addWidget(meta)

        right.addStretch(1)

        bar = QProgressBar()
        bar.setRange(0, 1000)
        pct = float(book.get("percent") or 0.0)
        bar.setValue(int(pct * 10))
        bar.setTextVisible(False)
        bar.setFixedHeight(4)
        right.addWidget(bar)

        foot = QLabel("已读 %.1f%%" % pct)
        foot.setObjectName("Muted")
        right.addWidget(foot)

        lay.addLayout(right, 1)

    # ------------------------------------------------------------ 交互
    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.sig_open.emit(int(self.book["id"]))
        super().mouseReleaseEvent(ev)

    def contextMenuEvent(self, ev):
        menu = QMenu(self)
        act_open = QAction("打开", menu)
        act_open.triggered.connect(lambda: self.sig_open.emit(int(self.book["id"])))
        menu.addAction(act_open)
        menu.addSeparator()
        act_del = QAction("从书架移除", menu)
        act_del.triggered.connect(lambda: self.sig_remove.emit(int(self.book["id"])))
        menu.addAction(act_del)
        menu.exec(ev.globalPos())


class BookshelfView(QWidget):
    sig_open_book = Signal(int)
    sig_status = Signal(str)

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.setAcceptDrops(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 18, 28, 18)
        root.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("书架")
        title.setObjectName("SectionTitle")
        head.addWidget(title)
        head.addStretch(1)
        self.btn_import = QPushButton("导入文档")
        self.btn_import.setObjectName("Primary")
        self.btn_import.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_import.clicked.connect(self.pick_files)
        head.addWidget(self.btn_import)
        root.addLayout(head)

        self.hint = QLabel("支持 .txt 与 .epub，可直接把文件拖进窗口")
        self.hint.setObjectName("Muted")
        root.addWidget(self.hint)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.container = QWidget()
        self.vbox = QVBoxLayout(self.container)
        self.vbox.setContentsMargins(0, 4, 6, 4)
        self.vbox.setSpacing(4)
        self.vbox.addStretch(1)
        self.scroll.setWidget(self.container)
        root.addWidget(self.scroll, 1)

        self.empty = QLabel("书架还是空的 —— 点右上角「导入文档」，或把 txt / epub 拖进来")
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self.empty)

        self.refresh()

    # ------------------------------------------------------------ 数据
    def refresh(self) -> None:
        while self.vbox.count() > 1:
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        books = self.library.list_books()
        for b in books:
            card = BookCard(b)
            card.sig_open.connect(self.sig_open_book)
            card.sig_remove.connect(self._remove)
            self.vbox.insertWidget(self.vbox.count() - 1, card)

        self.empty.setVisible(not books)
        self.scroll.setVisible(bool(books))

    def _remove(self, book_id: int) -> None:
        book = self.library.get_book(book_id)
        if not book:
            return
        ans = QMessageBox.question(
            self, "从书架移除",
            "「%s」\n\n只从书架移除记录，不会删除磁盘上的原文件。确定吗？" % book["title"],
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self.library.remove_book(book_id)
            self.refresh()

    # ------------------------------------------------------------ 导入
    def pick_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "选择文档", "",
            "文本与电子书 (*.txt *.epub);;文本文件 (*.txt);;EPUB (*.epub);;所有文件 (*.*)")
        if paths:
            self.import_paths(paths)

    def import_paths(self, paths) -> bool:
        ok, bad = [], []
        for p in paths:
            ext = os.path.splitext(p)[1].lower()
            if ext not in SUPPORTED_EXTS:
                bad.append(os.path.basename(p))
                continue
            bid = self.library.add_file(p)
            (ok if bid else bad).append(os.path.basename(p))
        self.refresh()
        msg = []
        if ok:
            msg.append("已导入 %d 个文档" % len(ok))
        if bad:
            msg.append("跳过 %d 个（格式不支持或文件不存在）" % len(bad))
        if msg:
            self.sig_status.emit("，".join(msg))
        return bool(ok)

    # ------------------------------------------------------------ 拖放
    def dragEnterEvent(self, ev):
        if ev.mimeData().hasUrls():
            ev.acceptProposedAction()

    def dropEvent(self, ev):
        paths = [u.toLocalFile() for u in ev.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.import_paths(paths)
            ev.acceptProposedAction()
