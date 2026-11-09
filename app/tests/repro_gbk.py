# -*- coding: utf-8 -*-
"""复现：打开 GBK 编码文件中途退出。"""
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.paginate import Layout, Paginator
from app.core.textfile import TextFile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
GBK = os.path.join(ROOT, "spike", "corpus", "gbk_20mb.txt")
TMP = os.path.join(ROOT, "build", "gbk_test")
os.makedirs(TMP, exist_ok=True)

app = QApplication([])

print("1) 采样判编码")
from app.core.textfile import probe_encoding
enc, conf = probe_encoding(GBK)
print("   ->", enc, round(conf, 2))

print("2) TextFile.open")
tf = TextFile(GBK).open()
print("   -> encoding=%s newline=%r size=%d" % (tf.encoding, tf.newline, tf.size))
print("   首 80 字: %r" % tf.read_window(0, 240)[:80])

print("3) 建索引")
n = tf.build_index()
print("   -> %d 行" % n)

print("4) 分页（连续 5 页）")
pg = Paginator(tf, Layout(780, 746, "Microsoft YaHei", 20, 1.8, 48, 36, "left"))
off = 0
for i in range(5):
    p = pg.layout_page(off)
    print("   第%d页 chars=%-4d %d..%d  首=%r" % (i + 1, p.chars, p.start, p.end, p.text[:12]))
    if p.is_empty:
        print("   !! 空页，提前中断")
        break
    off = p.end

print("5) 中途偏移分页")
for off in (1_000_000, 7_000_000, 14_000_000):
    p = pg.layout_page(off)
    print("   off=%-9d chars=%-4d 首=%r" % (off, p.chars, p.text[:14]))

print("6) 走 Library + ReaderView 完整打开")
from app.ui.main_window import MainWindow
from app.core.settings import Settings
from app.ui.theme import build_qss

settings = Settings(os.path.join(TMP, "s.json"))
lib = Library(os.path.join(TMP, "l.db"))
bid = lib.add_file(GBK)
print("   book_id =", bid, "encoding =", lib.get_book(bid)["encoding"])
win = MainWindow(settings, lib, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
app.processEvents()
try:
    ok = win.open_book(bid)
    app.processEvents()
    print("   open_book ->", ok, "| 页字符", win.reader.page.chars)
    win.reader.next_page()
    app.processEvents()
    print("   翻页后", win.reader.page.chars, "字")
except Exception:
    traceback.print_exc()

win.hide()
lib.close()
tf.close()
print("完成")
