# -*- coding: utf-8 -*-
"""滚动/分页两种模式的像素级校验：正文实际占位必须落在正文栏内。"""
import os
import sys

from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "pixel_test")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])
settings = Settings(os.path.join(TMP, "s.json"))
library = Library(os.path.join(TMP, "p.db"))
bid = library.add_file(BIG)

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()
win.open_book(bid)
app.processEvents()
reader = win.reader


def bounds(mode_label):
    app.processEvents()
    pm = reader.grab()
    img = pm.toImage()
    bg = img.pixelColor(3, 3)
    minx, maxx = 10 ** 6, -1
    miny, maxy = 10 ** 6, -1
    for y in range(0, img.height() - 40):
        for x in range(0, img.width()):
            if img.pixelColor(x, y) != bg:
                if x < minx:
                    minx = x
                if x > maxx:
                    maxx = x
                if y < miny:
                    miny = y
                if y > maxy:
                    maxy = y
    lay = reader.pg.layout
    col_x = (reader.width() - lay.width) / 2
    print("  %-8s 像素正文 x[%d,%d] y[%d,%d] | 正文栏 x[%.0f,%.0f] 宽 %.0f"
          % (mode_label, minx, maxx, miny, maxy, col_x, col_x + lay.width, lay.width))
    return minx, maxx, col_x


print("窗口 1120x780：")
reader.set_mode("paginate")
app.processEvents()
a = bounds("分页")
reader.set_mode("scroll")
for _ in range(2):
    reader.scroll_by(300)
b = bounds("滚动")

ok = True
for name, (minx, maxx, col_x) in (("分页", a), ("滚动", b)):
    if minx < col_x - 4:
        print("  ✗ %s：左边界 %d 越过正文栏 %.0f" % (name, minx, col_x))
        ok = False
    if maxx > col_x + 780 + 4:
        print("  ✗ %s：右边界 %d 越过正文栏右沿 %.0f" % (name, maxx, col_x + 780))
        ok = False

win.hide()
library.close()
print("结论:", "通过" if ok else "不通过")
sys.exit(0 if ok else 1)
