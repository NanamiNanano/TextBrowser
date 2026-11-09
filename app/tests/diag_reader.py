# -*- coding: utf-8 -*-
"""诊断阅读器内部实际生效的版式参数（与截图逐项对照）。"""
import os

from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "shot_tmp")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])
settings = Settings(os.path.join(TMP, "settings.json"))
library = Library(os.path.join(TMP, "diag.db"))
bid = library.add_file(BIG)

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()

win.open_book(bid)
app.processEvents()

r = win.reader
pg = r.pg
print("窗口            %dx%d" % (win.width(), win.height()))
print("阅读器控件      %dx%d" % (r.width(), r.height()))
print("layout.width    %s" % pg.layout.width)
print("layout.height   %s" % pg.layout.height)
print("margin_h/v      %s / %s" % (pg.layout.margin_h, pg.layout.margin_v))
print("content_width   %.1f" % pg.content_width)
print("content_height  %.1f" % pg.content_height)
ds = pg.doc.documentLayout().documentSize()
print("文档尺寸        %.1fx%.1f" % (ds.width(), ds.height()))
print("页字符          %d" % r.page.chars)
print("绘制原点 x      %.1f   -> 文字右边界 %.1f" % ((r.width() - pg.layout.width) / 2,
                                               (r.width() + pg.layout.width) / 2))
print("理论右边界      %.1f" % ((r.width() - pg.layout.width) / 2 + pg.content_width))
print("首行            %r" % r.page.text.split("\n")[0][:30])

# 客观校验：扫描截图像素，找正文实际占据的左右边界（不靠肉眼）
app.processEvents()
pm = r.grab()
img = pm.toImage()
bg = img.pixelColor(2, 2)
minx, maxx = 10 ** 6, -1
for y in range(0, img.height() - 40, 2):          # 跳过页脚
    for x in range(0, img.width(), 1):
        if img.pixelColor(x, y) != bg:
            if x < minx:
                minx = x
            if x > maxx:
                maxx = x
print("像素实测正文 x  [%d, %d]  宽 %d" % (minx, maxx, maxx - minx + 1))
print("理论正文区 x    [%.0f, %.0f]  宽 %.0f"
      % ((r.width() - pg.layout.width) / 2,
         (r.width() + pg.layout.width) / 2,
         pg.content_width))

win.hide()
library.close()
