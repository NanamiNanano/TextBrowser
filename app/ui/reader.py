# -*- coding: utf-8 -*-
"""阅读视图：分页 / 滚动两种模式、Q/E 翻页、进度保存、搜索高亮、页码估算。

两种模式的共同基准都是「字节偏移」：
  * 分页模式：一页 = 一屏，页边界由 Paginator 逐页求得；
  * 滚动模式：一次排一块约 2.4 屏的文本，滚动只是在块内平移；滚到块尾时
    以「当前可见首行」为新起点重排下一块。这样滚动不需要每帧排版。

页码不再是会话内计数，而是用「已排版页的平均字节数」把偏移换算成全书页码，
因此跨会话稳定，改字号后会随新页宽自然变化（估算值，界面标注「约」）。
"""
import time
from bisect import bisect_left, bisect_right

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QWidget

from ..core.paginate import Layout, Page, Paginator
from ..core.textfile import TextFile
from .theme import mix

FOOTER_H = 34
SCROLL_CHUNK_SCREENS = 2.4      # 滚动模式一次排版多少屏
SCROLL_STEP = 0.9               # Q/E 在滚动模式下一次移动多少屏


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
        self._reset_page_stats()

        # 章节表：偏移数组供二分定位当前章节，标题数组按下标取
        self._chap_offsets = []
        self._chap_titles = []

        # 搜索命中：[(字节偏移, 字节长度)]，按偏移升序
        self._hits = []
        self._hit_offsets = []
        self._current_hit = None

        # 滚动模式状态
        self._scroll_start = 0
        self._scroll_y = 0.0
        self._scroll_history = []
        self._scroll_enc = "utf-8"

    # ------------------------------------------------------------ 模式
    def is_scroll_mode(self) -> bool:
        return self.settings.get("reading.mode", "paginate") == "scroll"

    def set_mode(self, mode: str) -> None:
        """切换分页 / 滚动，保持阅读位置。"""
        if mode not in ("paginate", "scroll"):
            return
        offset = self.top_offset()
        self.settings.set("reading.mode", mode)
        if self.tf is None:
            return
        self._scroll_history.clear()
        self._scroll_y = 0.0
        # 刻意不重置页码统计：两种模式的「每页字节数」已按有效高度折算，
        # 复用同一份平均值才能保证切换后页码连续、不跳号。
        self._apply_layout(offset)
        self.update()
        self._notify()

    # ------------------------------------------------------------ 生命周期
    def open_book(self, book: dict, path: str = None) -> bool:
        """path 可覆盖实际读取的文件：EPUB 会读转换后的纯文本缓存。"""
        self.close_book()
        path = path or book["file_path"]
        try:
            tf = TextFile(path, encoding=book.get("encoding"))
            tf.open()
        except OSError as e:
            self.sig_status.emit("打开失败：%s" % e)
            return False

        self.tf = tf
        self._scroll_enc = tf.encoding or "utf-8"
        self.book = book
        self._history.clear()
        self._scroll_history.clear()
        self._scroll_y = 0.0
        self._reset_page_stats()

        prog = self.library.get_progress(int(book["id"]))
        offset = int(prog.get("offset") or 0)
        if offset >= tf.size:
            offset = 0

        self._apply_layout(offset)
        self.setFocus()
        self.update()
        self.sig_status.emit("%s · %s" % (book["title"], book.get("encoding") or "?"))
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
        self._scroll_start = 0
        self._scroll_y = 0.0
        self._scroll_history.clear()

    # ------------------------------------------------------------ 版式
    @property
    def view_height(self) -> int:
        """正文可视高度（不含页脚）。"""
        return max(120, self.height() - FOOTER_H)

    def _make_layout(self, for_scroll: bool = False) -> Layout:
        a = self.settings.data["appearance"]
        margin_h = int(a["marginH"])
        margin_v = int(a["marginV"])
        avail_h = self.view_height
        if for_scroll:
            # 滚动模式下一块要比一屏高，才有块内平移的余地
            avail_h = int(avail_h * SCROLL_CHUNK_SCREENS)
        col = min(max(320, self.width() - margin_h * 2), int(a["maxContentWidth"]))
        return Layout(
            width=float(col),
            height=float(avail_h),
            font_family=a["fontFamily"],
            font_px=int(a["fontSize"]),
            line_height=float(a["lineHeight"]),
            margin_h=float(margin_h),
            margin_v=float(margin_v),
            align=a["align"],
            indent_chars=float(a["textIndent"]),
            text_color=a["textColor"],
            letter_spacing=float(a.get("letterSpacing") or 0.0),
        )

    def _apply_layout(self, offset=None, layout=None) -> None:
        """重建分页器并立刻重排。

        必须「重建 + 重排」一起做：新建的 Paginator 文档是空的，只重建不重排会
        留下空文档，表现就是拖窗口后正文变白、翻页才回来。
        """
        if self.tf is None:
            return
        start = self.page.start if offset is None else offset
        if self.is_scroll_mode():
            self.pg = Paginator(self.tf, layout or self._make_layout(for_scroll=True))
            self._scroll_start = max(0, min(start, max(0, self.tf.size - 1)))
            self._scroll_y = 0.0
            self.page = self.pg.layout_page(self._scroll_start)
            # 一块 = 2.4 屏，折算成每屏字节数才能算页码
            self._sample_page_bytes(self.page, self._scroll_divisor())
        else:
            self.pg = Paginator(self.tf, layout or self._make_layout())
            self.page = self.pg.layout_page(start)
            self._sample_page_bytes(self.page)
        self._refresh_highlights()

    def apply_appearance(self) -> None:
        """外观设置变化后重新排版，保持当前位置（字节偏移不变）。"""
        if self.tf is None:
            return
        self._reset_page_stats()
        self._apply_layout(self.top_offset())
        self.update()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        if self.tf is not None and self.pg is not None:
            candidate = self._make_layout(for_scroll=self.is_scroll_mode())
            if candidate.signature() != self.pg.layout.signature():
                self._reset_page_stats()
                self._apply_layout(self.top_offset(), candidate)
        self.update()

    # ------------------------------------------------------------ 页码估算
    def _reset_page_stats(self) -> None:
        self._avg_page_bytes = 0.0
        self._samples = 0

    def _paginate_content_height(self) -> float:
        """分页模式下「一页」的有效正文高度。"""
        margin_v = float(self.settings.data["appearance"].get("marginV") or 0)
        return max(60.0, self.view_height - margin_v * 2)

    def _scroll_divisor(self) -> float:
        """滚动模式一块文本相当于多少「分页页」。

        不能直接用 SCROLL_CHUNK_SCREENS：分页模式扣两次页边距、滚动模式也扣两次，
        但两者基准高度不同，直接用 2.4 会让两模式的书页总数对不上（实测 103k vs 78k）。
        按实际有效高度折算，两个模式算出来的页数才一致。
        """
        margin_v = float(self.settings.data["appearance"].get("marginV") or 0)
        scroll_h = max(60.0, self.view_height * SCROLL_CHUNK_SCREENS - margin_v * 2)
        return max(1.0, scroll_h / self._paginate_content_height())

    def _sample_page_bytes(self, page: Page, divisor: float = 1.0) -> None:
        """累加页字节数做估算。

        采够 5 页就冻结平均值：否则用户一边读、平均值一边变，会出现
        「第 3 / 110855 页」变成「第 3 / 103702 页」这种自相矛盾的显示。
        """
        if self._samples >= 5:
            return
        n = (page.end - page.start) / max(1.0, divisor)
        if n <= 0:
            return
        if self._avg_page_bytes <= 0:
            self._avg_page_bytes = float(n)
        else:
            self._avg_page_bytes = self._avg_page_bytes * 0.8 + n * 0.2
        self._samples += 1

    def page_number(self) -> int:
        if self._avg_page_bytes <= 0:
            return 1
        return max(1, int(self.top_offset() / self._avg_page_bytes) + 1)

    def total_pages(self) -> int:
        if self._avg_page_bytes <= 0 or self.tf is None:
            return 0
        return max(1, int(round(self.tf.size / self._avg_page_bytes)))

    # ------------------------------------------------------------ 章节
    def set_chapters(self, chapters) -> None:
        self._chap_offsets = [int(c["start_off"]) for c in chapters]
        self._chap_titles = [c["title"] for c in chapters]
        self.update()

    def current_chapter_index(self) -> int:
        if not self._chap_offsets or self.tf is None:
            return -1
        return bisect_right(self._chap_offsets, self.top_offset()) - 1

    def current_chapter_title(self):
        i = self.current_chapter_index()
        if 0 <= i < len(self._chap_titles):
            return self._chap_titles[i]
        return None

    # ------------------------------------------------------------ 搜索高亮
    def set_search_hits(self, hits, current=None) -> None:
        self._hits = list(hits or ())
        self._hit_offsets = [h[0] for h in self._hits]
        self._current_hit = current
        self._refresh_highlights()

    def clear_search_hits(self) -> None:
        self.set_search_hits([], None)

    def _page_byte_range(self):
        """当前文档覆盖的字节区间。"""
        if self.is_scroll_mode():
            return self._scroll_start, self.page.end
        return self.page.start, self.page.end

    def _refresh_highlights(self) -> None:
        if self.pg is None or not self.page.text:
            return
        if not self._hits:
            self.pg.set_highlights([], None)
            return

        enc = self.tf.encoding or "utf-8"
        pstart, pend = self._page_byte_range()
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

    # ------------------------------------------------------------ 位置
    def top_offset(self) -> int:
        """当前可见区顶部的字节偏移——进度、页码、章节都以它为准。"""
        if self.tf is None:
            return 0
        if not self.is_scroll_mode():
            return self.page.start
        if self._scroll_y <= 0:
            return self._scroll_start
        return self._scroll_start + self._bytes_consumed(self._scroll_y)

    def _bytes_consumed(self, y: float) -> int:
        """块内从顶部到 y 像素处消耗了多少字节。"""
        if not self.page.text:
            return 0
        pos = self.pg.doc.documentLayout().hitTest(
            QPointF(self.pg.content_width / 2, max(0.0, y)),
            Qt.HitTestAccuracy.FuzzyHit)
        pos = int(pos) if pos and pos > 0 else 0
        try:
            return len(self.page.text[:pos].encode(self._scroll_enc, "ignore"))
        except LookupError:
            return 0

    def percent(self) -> float:
        if self.tf is None or not self.tf.size:
            return 0.0
        return min(100.0, self.top_offset() / self.tf.size * 100.0)

    def _save_progress(self, force: bool = False) -> None:
        if self.book is None:
            return
        now = time.monotonic()
        if not force and now - self._last_save < 1.0:
            return
        self._last_save = now
        self.library.save_progress(int(self.book["id"]), self.top_offset(), self.percent())

    def _notify(self) -> None:
        self.update()
        self.sig_progress.emit(self.top_offset(), self.percent())
        self._save_progress()

    # ------------------------------------------------------------ 翻页
    def next_page(self) -> bool:
        if self.tf is None:
            return False
        if self.is_scroll_mode():
            return self.scroll_by_screen(1)
        if self.page.is_empty:
            return False
        if self.page.end >= self.tf.size:
            self.sig_status.emit("已经到最后一页")
            return False
        self._history.append(self.page.start)
        self.page = self.pg.layout_page(self.page.end)
        self._sample_page_bytes(self.page)
        self._after_turn()
        return True

    def prev_page(self) -> bool:
        if self.tf is None:
            return False
        if self.is_scroll_mode():
            return self.scroll_by_screen(-1)
        if self._history:
            start = self._history.pop()
            self.page = self.pg.layout_page(start)
            self._after_turn()
            return True
        if self.page.start <= 0:
            self.sig_status.emit("已经是第一页")
            return False
        guess = max(0, self.page.start - max(600, len(self.page.text) * 3))
        self.page = self.pg.layout_page(guess)
        self._after_turn()
        return True

    def _after_turn(self) -> None:
        self._refresh_highlights()      # 换页后命中集合变了，要重新上色
        self._notify()

    # ------------------------------------------------------------ 滚动
    def scroll_by_screen(self, direction: int) -> bool:
        step = self.view_height * SCROLL_STEP
        return self.scroll_by(step * (1 if direction > 0 else -1))

    def scroll_by(self, dy: float) -> bool:
        if not self.is_scroll_mode() or self.tf is None:
            return False
        content_h = self.pg.doc.documentLayout().documentSize().height()
        view_h = max(40.0, self.pg.content_height / SCROLL_CHUNK_SCREENS)
        limit = content_h - view_h

        new_y = self._scroll_y + dy

        # 滚过块尾：以当前可见首行为起点排下一块
        while new_y > limit:
            if self.page.end >= self.tf.size:
                new_y = max(0.0, limit)
                self.sig_status.emit("已经到底了")
                break
            if not self._advance_chunk():
                break
            new_y -= limit
            content_h = self.pg.doc.documentLayout().documentSize().height()
            view_h = max(40.0, self.pg.content_height / SCROLL_CHUNK_SCREENS)
            limit = content_h - view_h

        # 滚过块首：回退一块
        while new_y < 0:
            if not self._rewind_chunk():
                new_y = 0.0
                break
            new_y += max(40.0, self.pg.content_height / SCROLL_CHUNK_SCREENS) * 0.5

        self._scroll_y = max(0.0, new_y)
        self._notify()
        return True

    def _advance_chunk(self) -> bool:
        consumed = self._bytes_consumed(self._scroll_y)
        new_start = self._scroll_start + max(1, consumed)
        if new_start >= self.tf.size:
            return False
        self._scroll_history.append((self._scroll_start, self._scroll_y))
        self._scroll_start = new_start
        self._scroll_y = 0.0
        self.page = self.pg.layout_page(new_start)
        self._sample_page_bytes(self.page, self._scroll_divisor())
        self._refresh_highlights()
        return True

    def _rewind_chunk(self) -> bool:
        if self._scroll_history:
            start, y = self._scroll_history.pop()
            self._scroll_start = start
            self.page = self.pg.layout_page(start)
            self._scroll_y = max(0.0, y)
            self._refresh_highlights()
            return True
        if self._scroll_start <= 0:
            return False
        guess = max(0, self._scroll_start - int(max(1.0, self._avg_page_bytes or 2000)))
        self._scroll_start = guess
        self.page = self.pg.layout_page(guess)
        self._scroll_y = 0.0
        self._refresh_highlights()
        return True

    def wheelEvent(self, ev):
        if self.tf is None:
            return
        if self.is_scroll_mode():
            dy = ev.angleDelta().y()
            if dy:
                self.scroll_by(-dy * 0.55)
                ev.accept()
                return
        super().wheelEvent(ev)

    # ------------------------------------------------------------ 跳转
    def goto_offset(self, offset: int, align_line: bool = False) -> None:
        """跳到指定字节偏移。

        align_line=True 时回退到该偏移所在行的行首：搜索命中常落在句子中间，
        直接从命中处开头会把半句话切在页顶。只有行内偏移不大时才回退，
        否则命中会被推出页外。
        """
        if self.tf is None:
            return
        offset = max(0, min(offset, self.tf.size - 1))
        if align_line:
            line_start = self.tf.line_start(self.tf.line_of_offset(offset))
            if offset - line_start <= 400:
                offset = line_start
        self._history.clear()
        self._scroll_history.clear()
        if self.is_scroll_mode():
            self._apply_layout(offset)
            self._notify()
            return
        self.page = self.pg.layout_page(offset)
        self._sample_page_bytes(self.page)
        self._after_turn()

    # ------------------------------------------------------------ 绘制
    def _col_geometry(self):
        lay = self.pg.layout
        return lay, (self.width() - lay.width) / 2.0

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

        lay, col_x = self._col_geometry()

        if self.is_scroll_mode():
            # 块内平移：文档顶端画在 margin_v - scroll_y，只露出正文可视区。
            # 裁剪框的 x 必须用正文栏的 col_x（居中后的左边界），用 margin_h
            # 会在窗口变宽时把右侧文字切掉。
            view_rect = QRectF(col_x, lay.margin_v, lay.width,
                               max(20, self.view_height - lay.margin_v * 2))
            p.save()
            p.setClipRect(view_rect)
            self.pg.draw(p, col_x, lay.margin_v - self._scroll_y)
            p.restore()
        else:
            self.pg.draw(p, col_x, lay.margin_v)

        self._paint_footer(p, bg, fg, lay, col_x)

    def _paint_footer(self, p, bg, fg, lay, col_x):
        if not self.settings.get("reading.showFooter", True):
            return
        fy = self.height() - FOOTER_H
        p.setPen(QColor(mix(bg.name(), fg.name(), 0.45)))
        f = QFont("Microsoft YaHei")
        f.setPixelSize(11)
        p.setFont(f)

        # 只显示「当前页码 + 两位小数百分比」，不显示全书页数：
        # 页数是用平均每页字节数估的，同一本书在分页/滚动两种模式下必然对不齐
        # （实测同一偏移的每像素字节数相差最多 10%），显示出来只会自相矛盾。
        # 百分比直接由「偏移 / 文件大小」得出，两种模式完全一致。
        right = "第 %d 页  ·  %.2f%%" % (self.page_number(), self.percent())

        rect = QRectF(col_x, fy + 6, lay.width, FOOTER_H - 12)
        fm = QFontMetrics(f)

        chapter = self.current_chapter_title()
        if chapter:
            reserved = fm.horizontalAdvance(right) + 24
            left = fm.elidedText(chapter, Qt.TextElideMode.ElideMiddle,
                                 max(40, int(lay.width - reserved)))
            p.drawText(rect, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter), left)

        p.drawText(rect, int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter), right)

    # ------------------------------------------------------------ 输入
    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            ev.ignore()
            return
        super().keyPressEvent(ev)
