# -*- coding: utf-8 -*-
"""分页引擎。

核心思路（实测 100MB 文本 ≈4.3ms/页）：
  * 从不把整本塞进 QTextDocument，只把当前页附近 ~6KB 切片交给它排版；
  * 用 QTextDocument.hitTest 求「页面底部坐标处的字符位置」，即本页末字；
  * 页与页之间用字节偏移衔接，翻页 = 一次切片 + 一次排版。

一次排版、多次绘制：layout_page() 算完边界后会把文档内容收敛成「正好这一页」，
之后 paintEvent 只需 drawContents，重绘不再付出排版成本。
"""
from dataclasses import dataclass
from typing import Optional

from PySide6.QtCore import QPointF, QSizeF, Qt
from PySide6.QtGui import (QColor, QFont, QTextBlockFormat, QTextCharFormat,
                           QTextCursor, QTextDocument, QTextOption)

from .textfile import TextFile

PROP_HEIGHT = int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)

MIN_WINDOW_BYTES = 6 * 1024
MAX_WINDOW_BYTES = 1024 * 1024


@dataclass
class Page:
    text: str
    start: int          # 起始字节偏移
    end: int            # 结束字节偏移（不含）
    chars: int

    @property
    def is_empty(self) -> bool:
        return not self.text


@dataclass
class Layout:
    width: float
    height: float
    font_family: str
    font_px: int
    line_height: float
    margin_h: float = 0.0
    margin_v: float = 0.0
    align: str = "justify"
    indent_chars: float = 0.0
    text_color: str = "#2B2B2B"
    letter_spacing: float = 0.0

    def signature(self) -> tuple:
        """版式指纹：任何一项变化都必须重新分页。"""
        return (round(self.width, 1), round(self.height, 1), self.font_family,
                self.font_px, round(self.line_height, 2),
                round(self.margin_h, 1), round(self.margin_v, 1),
                self.align, self.indent_chars, self.text_color,
                round(self.letter_spacing, 2))


class Paginator:
    def __init__(self, tf: TextFile, layout: Layout):
        self.tf = tf
        self.layout = layout
        self._color = QColor(layout.text_color)
        self.doc = self._make_doc()

    # ------------------------------------------------------------ 文档
    def _make_doc(self) -> QTextDocument:
        d = QTextDocument()
        d.setDocumentMargin(0)
        f = QFont(self.layout.font_family)
        f.setPixelSize(self.layout.font_px)
        if self.layout.letter_spacing:
            f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing,
                               self.layout.letter_spacing)
        d.setDefaultFont(f)
        d.setPageSize(QSizeF(self.content_width, self.content_height))
        opt = d.defaultTextOption()
        opt.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        if self.layout.align == "justify":
            opt.setAlignment(Qt.AlignmentFlag.AlignJustify)
        d.setDefaultTextOption(opt)
        return d

    @property
    def content_width(self) -> float:
        return max(80.0, self.layout.width - self.layout.margin_h * 2)

    @property
    def content_height(self) -> float:
        return max(60.0, self.layout.height - self.layout.margin_v * 2)

    def set_text_color(self, color: str) -> None:
        self._color = QColor(color)
        self.layout.text_color = color
        if getattr(self, "_page_text", None) is not None:
            self._apply(self._page_text)

    # ------------------------------------------------------------ 高亮
    def set_highlights(self, ranges=None, current=None) -> None:
        """给页面文本的若干字符区间加底色（搜索命中）。

        ranges 是「页内字符下标」区间 [(start, end)]，不是字节偏移——字节到字符
        的换算由调用方做，因为只有它知道本页起点。
        """
        self._highlights = list(ranges or ())
        self._highlight_current = current
        if getattr(self, "_page_text", None) is not None:
            self._apply(self._page_text)

    # ------------------------------------------------------------ 排版
    def _apply(self, text: str) -> None:
        d = self.doc
        d.setPlainText(text)
        cur = QTextCursor(d)
        cur.select(QTextCursor.SelectionType.Document)
        bf = QTextBlockFormat()
        bf.setLineHeight(self.layout.line_height * 100.0, PROP_HEIGHT)
        if self.layout.indent_chars:
            bf.setTextIndent(self.layout.indent_chars * self.layout.font_px)
        cur.mergeBlockFormat(bf)
        cf = QTextCharFormat()
        cf.setForeground(self._color)
        cur.mergeCharFormat(cf)

        # 命中区间用半透明底色，深浅主题下都不会盖住文字
        n = len(text)
        for rng in getattr(self, "_highlights", ()):
            s = max(0, min(int(rng[0]), n))
            e = max(0, min(int(rng[1]), n))
            if e <= s:
                continue
            hf = QTextCharFormat()
            is_cur = self._highlight_current == (s, e)
            hf.setBackground(QColor(255, 168, 0, 150) if is_cur
                             else QColor(255, 214, 64, 110))
            hc = QTextCursor(d)
            hc.setPosition(s)
            hc.setPosition(e, QTextCursor.MoveMode.KeepAnchor)
            hc.mergeCharFormat(hf)

        self._page_text = text
        d.documentLayout().documentSize()   # 强制完成排版

    def _capacity(self, text: str) -> int:
        """把 text 排进去，返回一页能容纳的字符数。"""
        self._apply(text)
        pos = self.doc.documentLayout().hitTest(
            QPointF(self.content_width / 2, self.content_height - 1),
            Qt.HitTestAccuracy.FuzzyHit)
        cut = int(pos) if pos and pos > 0 else len(text)
        # 页底若正好落在换行符上，跳过它，避免下一页以空行开头
        while cut < len(text) and text[cut] == "\n":
            cut += 1
        return cut

    def layout_page(self, start: int, window: int = MIN_WINDOW_BYTES) -> Page:
        """从字节偏移 start 开始排出一页。"""
        total = self.tf.size
        start = self.tf.align_offset(start)      # 不落在多字节字符中间
        if total == 0 or start >= total:
            self._apply("")
            return Page("", total, total, 0)

        while True:
            text = self.tf.read_window(start, window)
            if not text:
                self._apply("")
                return Page("", total, total, 0)
            cut = self._capacity(text)

            if 0 < cut < len(text):
                break
            if cut >= len(text) and start + window < total and window < MAX_WINDOW_BYTES:
                window *= 2                     # 窗口装不满一页，翻倍重试
                continue
            cut = max(1, min(len(text), cut or 1))
            break

        page_text = text[:cut]
        consumed = len(page_text.encode(self.tf.encoding or "utf-8", errors="ignore"))
        if consumed <= 0:
            consumed = 1
        # 收敛文档内容为「正好这一页」，后续绘制不再排版
        self._apply(page_text)
        return Page(page_text, start, min(start + consumed, total), len(page_text))

    def page_from_line(self, line_index: int) -> Page:
        return self.layout_page(self.tf.line_start(line_index))

    def draw(self, painter, origin_x: float, origin_y: float) -> None:
        """把已排好的一页画出来（不触发布局计算）。"""
        painter.save()
        painter.translate(origin_x, origin_y)
        self.doc.drawContents(painter)
        painter.restore()
