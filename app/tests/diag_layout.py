# -*- coding: utf-8 -*-
"""分页版式的实测诊断：检查栏宽、每页字数、页高利用率。"""
import os
import sys

from PySide6.QtWidgets import QApplication

from app.core.paginate import Layout, Paginator
from app.core.textfile import TextFile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")

app = QApplication.instance() or QApplication([])

tf = TextFile(BIG).open()
print("encoding=%s size=%.1fMB" % (tf.encoding, tf.size / 1048576))

for (w, h, mh, mv, footer) in [(1120, 780, 48, 36, 34), (760, 620, 48, 36, 34)]:
    avail_h = h - footer
    col = min(max(320, w - mh * 2), 780)
    lay = Layout(width=float(col), height=float(avail_h),
                 font_family="Microsoft YaHei", font_px=20, line_height=1.8,
                 margin_h=float(mh), margin_v=float(mv), align="left")
    pg = Paginator(tf, lay)
    page = pg.layout_page(0)
    doc_size = pg.doc.documentLayout().documentSize()
    print("\n窗口 %dx%d  footer=%d" % (w, h, footer))
    print("  layout.width=%d  content_width=%.0f  content_height=%.0f"
          % (col, pg.content_width, pg.content_height))
    print("  文档尺寸=%.0fx%.0f  页字符=%d" % (doc_size.width(), doc_size.height(), page.chars))
    # 页高利用率
    print("  页高利用率=%.1f%%  (文字实际高 %.0f / 可用 %.0f)"
          % (doc_size.height() / pg.content_height * 100, doc_size.height(), pg.content_height))
    print("  首行=%r" % page.text.split("\n")[0][:24])
    print("  末行=%r" % page.text.split("\n")[-2][:24] if page.text.count("\n") > 1 else "")

# 中文字符被切断的情况：从任意偏移开始
print("\n=== 任意偏移的字符对齐检查 ===")
bad = 0
for off in [24_000_000, 12_345_678, 50_000_001, 77_777_777]:
    text = tf.read_window(off, 60)
    if text and text[0] == "\ufffd":
        bad += 1
        print("  偏移 %-10d 首字符是替换符 -> 需要对齐" % off)
    else:
        print("  偏移 %-10d 首字符=%r" % (off, text[:6]))
print("未对齐样本: %d/4" % bad)

tf.close()
