# -*- coding: utf-8 -*-
"""阅读视图：分页渲染、Q/E 翻页、进度保存、搜索高亮。"""
import time
from bisect import bisect_left, bisect_right

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..core.paginate import Layout, Page, Paginator
from ..core.textfile import TextFile
from .theme import mix

FOOTER_H = 34


class ReaderView(QWidget):
    sig_progress = Signal(int, float)     # 字节偏移, 百分比
    sig_status = Signal(str)
    sig_closed = Signal()

    def __init__(self, settings, library, parent=None):
        super().__init__(parent)
        self.settings = settings
        self.library = library
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAutoFillBackground(False)

        self.tf = None
        self.pg = None
        self.page: Page = Page("", 0, 0, 0)
        self.book = None
        self._history = []
        self._last_save = 0.0
        self._page_no = 1
        # 章节表：偏移数组供二分定位当前章节，标题数组按下标取
        self._chap_offsets = []
        self._chap_titles = []
        # 搜索命中：[(字节偏移, 字节长度)]，按偏移升序
        self._hits = []
        self._hit_offsets = []
        self._current_hit = None

    # ------------------------------------------------------------ 生命周期
    def open_book(self, book: dict) -> bool:
        self.close_book()
        path = book["file_path"]
        try:
            tf = TextFile(path, encoding=book.get("encoding"))
            tf.open()
        except OSError as e:
            self.sig_status.emit("打开失败：%s" % e)
            return False

        self.tf = tf
        self.book = book
        self._history.clear()
        self._page_no = 1

        prog = self.library.get_progress(int(book["id"]))
        offset = int(prog.get("offset") or 0)
        if offset >= tf.size:
            offset = 0

        self._apply_layout(offset)
        self.setFocus()
        self.update()
        self.sig_status.emit("%s · %s · %s" % (
            book["title"], book.get("encoding") or "?", tf.newline.strip("'\\r\\n'") or "\\n"))
        return True

    def close_book(self) -> None:
        if self.tf is not None:
            self._save_progress(force=True)
            self.tf.close()
            self.tf = None
        self.pg = None
        self.book = None
        self.page = Page("", 0, 0, 0)
        self._history.clear()
        self._chap_offsets = []
        self._chap_titles = []
        self._hits = []
        self._hit_offsets = []
        self._current_hit = None

    # ------------------------------------------------------------ 版式
    def _make_layout(self) -> Layout:
        a = self.settings.data["appearance"]
        margin_h = int(a["marginH"])
        avail_h = max(200, self.height() - FOOTER_H)
        col = min(max(320, self.width() - margin_h * 2), int(a["maxContentWidth"]))
        return Layout(
            width=float(col),
            height=float(avail_h),
            font_family=a["fontFamily"],
            font_px=int(a["fontSize"]),
            line_height=float(a["lineHeight"]),
            margin_h=float(margin_h),
            margin_v=float(a["marginV"]),
            align=a["align"],
            indent_chars=float(a["textIndent"]),
            text_color=a["textColor"],
            letter_spacing=float(a.get("letterSpacing") or 0.0),
        )

    def _apply_layout(self, offset=None, layout=None) -> None:
        """按当前设置重建分页器，并从指定偏移重排一页。

        必须「重建 + 立刻重排」一起做，不能拆开：新建的 Paginator 文档是空的，
        只重建不重排会留下一个空文档，表现就是拖窗口后正文变白、翻页才回来。
        """
        if self.tf is None:
            return
        start = self.page.start if offset is None else offset
        self.pg = Paginator(self.tf, layout or self._make_layout())
        self.page = self.pg.layout_page(start)
        self._refresh_highlights()

    # ------------------------------------------------------------ 搜索高亮
    def set_search_hits(self, hits, current=None) -> None:
        """hits: [(字节偏移, 字节长度)]，按偏移升序；current 为当前跳转到的命中。"""
        self._hits = list(hits or ())
        self._hit_offsets = [h[0] for h in self._hits]
        self._current_hit = current
        self._refresh_highlights()

    def clear_search_hits(self) -> None:
        self.set_search_hits([], None)

    def _refresh_highlights(self) -> None:
        """把落在当前页内的命中换算成页内字符区间，交给分页器上色。"""
        if self.pg is None or self.page.is_empty:
            return
        if not self._hits:
            self.pg.set_highlights([], None)
            return

        enc = self.tf.encoding or "utf-8"
        pstart, pend = self.page.start, self.page.end
        i = bisect_left(self._hit_offsets, pstart)
        j = bisect_left(self._hit_offsets, pend)

        ranges = []
        current = None
        for off, length in self._hits[i:j]:
            if off + length > pend:
                continue
            try:
                prefix = self.tf.read_bytes(pstart, off - pstart).decode(enc, "ignore")
                body = self.tf.read_bytes(off, length).decode(enc, "ignore")
            except LookupError:
                continue
            s = len(prefix)
            e = s + len(body)
            if e <= s:
                continue
            ranges.append((s, e))
            if self._current_hit is not None and self._current_hit[0] == off:
                current = (s, e)
        self.pg.set_highlights(ranges, current)

    def apply_appearance(self) -> None:
        """外观设置变化后重新分页，保持当前位置（字节偏移不变）。"""
        if self.tf is None:
            return
        self._apply_layout(self.page.start)
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.tf is not None and self.pg is not None:
            # 先算新版式再决定要不要重建。正文栏宽度被 maxContentWidth 卡住时，
            # 拖宽窗口并不会改变版式，此时重排是白费；但一旦重建就必须重排。
            candidate = self._make_layout()
            if candidate.signature() != self.pg.layout.signature():
                self._apply_layout(self.page.start, candidate)
        self.update()

    # ------------------------------------------------------------ 翻页
    def next_page(self) -> bool:
        if self.tf is None or self.page.is_empty:
            return False
        if self.page.end >= self.tf.size:
            self.sig_status.emit("已经到最后一页")
            return False
        self._history.append(self.page.start)
        self._page_no += 1
        self.page = self.pg.layout_page(self.page.end)
        self._after_turn()
        return True

    def prev_page(self) -> bool:
        if self.tf is None:
            return False
        if self._history:
            start = self._history.pop()
            self._page_no = max(1, self._page_no - 1)
            self.page = self.pg.layout_page(start)
            self._after_turn()
            return True
        # 没有历史：向前回退约一页的量
        if self.page.start <= 0:
            self.sig_status.emit("已经是第一页")
            return False
        guess = max(0, self.page.start - max(600, len(self.page.text) * 3))
        self.page = self.pg.layout_page(guess)
        self._page_no = max(1, self._page_no - 1)
        self._after_turn()
        return True

    # ------------------------------------------------------------ 章节
    def set_chapters(self, chapters) -> None:
        """chapters: [{'start_off': int, 'title': str, ...}]，按 start_off 升序。"""
        self._chap_offsets = [int(c["start_off"]) for c in chapters]
        self._chap_titles = [c["title"] for c in chapters]
        self.update()

    def current_chapter_index(self) -> int:
        if not self._chap_offsets or self.tf is None:
            return -1
        return bisect_right(self._chap_offsets, self.page.start) - 1

    def current_chapter_title(self):
        i = self.current_chapter_index()
        if 0 <= i < len(self._chap_titles):
            return self._chap_titles[i]
        return None

    def goto_offset(self, offset: int, align_line: bool = False) -> None:
        """跳到指定字节偏移。

        align_line=True 时回退到该偏移所在行的行首：搜索命中常常落在句子中间，
        直接从命中处开头会把半句话切在页顶，看不出上下文。只有在本行不太长时
        才回退，否则命中会被推到页外去。
        """
        if self.tf is None:
            return
        offset = max(0, min(offset, self.tf.size - 1))
        if align_line:
            line_start = self.tf.line_start(self.tf.line_of_offset(offset))
            if offset - line_start <= 400:
                offset = line_start
        self._history.clear()
        self.page = self.pg.layout_page(offset)
        self._after_turn()

    def _after_turn(self) -> None:
        self._refresh_highlights()      # 换页后命中集合变了，要重新上色
        self.update()
        pct = self.percent()
        self.sig_progress.emit(self.page.start, pct)
        self._save_progress()

    def percent(self) -> float:
        if self.tf is None or not self.tf.size:
            return 0.0
        return min(100.0, self.page.start / self.tf.size * 100.0)

    def _save_progress(self, force: bool = False) -> None:
        if self.book is None:
            return
        now = time.monotonic()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now
        self.library.save_progress(int(self.book["id"]), self.page.start, self.percent())

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        bg = QColor(self.settings.get("appearance.bgColor", "#F5EFE0"))
        fg = QColor(self.settings.get("appearance.textColor", "#2B2B2B"))
        p.fillRect(self.rect(), bg)

        if self.tf is None or self.pg is None:
            p.setPen(QColor(mix(bg.name(), fg.name(), 0.5)))
            f = QFont("Microsoft YaHei")
            f.setPixelSize(15)
            p.setFont(f)
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "从书架选一本书开始阅读")
            return

        lay = self.pg.layout
        col_x = (self.width() - lay.width) / 2.0
        self.pg.draw(p, col_x, lay.margin_v)

        # 页脚（与正文栏对齐，不要用整窗宽度，否则窄栏时左右会错位）
        if self.settings.get("reading.showFooter", True):
            fy = self.height() - FOOTER_H
            p.setPen(QColor(mix(bg.name(), fg.name(), 0.45)))
            f = QFont("Microsoft YaHei")
            f.setPixelSize(11)
            p.setFont(f)
            right = "第 %d 页  ·  %.1f%%" % (self._page_no, self.percent())
            rect = QRectF(col_x, fy + 6, lay.width, FOOTER_H - 12)
            fm = QFontMetrics(f)

            # 左边放当前章节名，右边固定放页码/进度；章节名过长就省略，
            # 并给右边预留宽度，避免两边文字撞在一起。
            chapter = self.current_chapter_title()
            if chapter:
                reserved = fm.horizontalAdvance(right) + 24
                left = fm.elidedText(chapter, Qt.TextElideMode.ElideMiddle,
                                     max(40, int(lay.width - reserved)))
                p.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), left)

            p.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right)

    # ------------------------------------------------------------ 输入
    def keyPressEvent(self, ev):
        k = ev.key()
        if k in (Qt.Key.Key_Escape,):
            ev.ignore()
            return
        super().keyPressEvent(ev)
