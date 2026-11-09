# -*- coding: utf-8 -*-
"""界面截图脚本：把窗口渲染成 PNG，供开发期自查（不需要人盯着屏幕）。

用法: python -m app.tests.shot_ui [输出目录]
"""
import os
import sys
import tempfile

from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "docs", "shots")
os.makedirs(OUT, exist_ok=True)

app = QApplication.instance() or QApplication([])


def snap(win, name, w=None, h=None):
    if w and h:
        win.resize(w, h)
    app.processEvents()
    pm = win.grab()
    path = os.path.join(OUT, name + ".png")
    pm.save(path)
    print("  %-28s %dx%d  %s" % (name, pm.width(), pm.height(), path))
    return path


def main():
    tmp = os.path.join(ROOT, "build", "shot_tmp")
    os.makedirs(tmp, exist_ok=True)
    settings = Settings(os.path.join(tmp, "settings.json"))
    library = Library(os.path.join(tmp, "library.db"))

    bid = library.add_file(BIG)
    # 造两本假书记录，让书架看起来有内容
    if bid:
        library.save_progress(bid, 24_000_000, 22.9)

    win = MainWindow(settings, library, enable_tray=False)
    app.setStyleSheet(build_qss(settings))
    win.show()
    app.processEvents()

    print("截图输出:")
    snap(win, "01_shelf", 1120, 780)

    if bid:
        win.open_book(bid)
        app.processEvents()
        snap(win, "02_reader_light", 1120, 780)

        # 翻几页，确认页眉页脚与进度
        for _ in range(3):
            win.reader.next_page()
        app.processEvents()
        snap(win, "03_reader_page4", 1120, 780)

        # 目录侧栏
        win._load_toc()
        win.toggle_toc()
        app.processEvents()
        snap(win, "07_reader_toc", 1120, 780)
        win.toggle_toc()
        app.processEvents()

        # 搜索侧栏 + 页内高亮
        win.toggle_search()
        win.search.input.setText("长夜将至")
        win.search.run_search()
        hits = win.search.current_hits()
        if hits:
            win._on_search_jump(hits[min(5, len(hits) - 1)].offset,
                                hits[min(5, len(hits) - 1)].length)
        app.processEvents()
        snap(win, "08_reader_search", 1120, 780)
        win.close_side()
        app.processEvents()

        # 深色主题
        settings.set("appearance.bgColor", "#2B2B2B")
        settings.set("appearance.textColor", "#C8C8C8")
        win.setStyleSheet(build_qss(settings))
        win.reader.apply_appearance()
        app.processEvents()
        snap(win, "04_reader_dark", 1120, 780)

        # 护眼绿 + 大字
        settings.set("appearance.bgColor", "#CCE8CF")
        settings.set("appearance.textColor", "#2A3A2C")
        settings.set("appearance.fontSize", 26)
        settings.set("appearance.lineHeight", 2.0)
        win.setStyleSheet(build_qss(settings))
        win.reader.apply_appearance()
        app.processEvents()
        snap(win, "05_reader_green_26px", 1120, 780)

        # 窄窗口（模拟半屏），验证分页重排
        settings.set("appearance.bgColor", "#F5EFE0")
        settings.set("appearance.textColor", "#2B2B2B")
        settings.set("appearance.fontSize", 18)
        win.setStyleSheet(build_qss(settings))
        win.reader.apply_appearance()
        snap(win, "06_reader_narrow", 760, 620)

    win.hide()
    library.close()
    print("\n完成。共 %d 张。" % len([f for f in os.listdir(OUT) if f.endswith(".png")]))


if __name__ == "__main__":
    main()
