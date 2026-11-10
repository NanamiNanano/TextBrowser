# -*- coding: utf-8 -*-
"""M5 测试：书签增删改查与界面联动。"""
import os
import sys
import traceback

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "m5")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])
passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-36s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-36s %s" % (name, e))
        traceback.print_exc()
        failed += 1


for f in ("m5.db", "m5.db-wal", "m5.db-shm", "s.json"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass

settings = Settings(os.path.join(TMP, "s.json"))
library = Library(os.path.join(TMP, "m5.db"))
bid = library.add_file(BIG)
assert bid, "语料缺失"

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()
win.open_book(bid)
app.processEvents()
win._stop_worker()
reader = win.reader

print("\n== 1. 存储层 ==")


def t_add():
    bid_ = int(reader.book["id"])
    bm = library.add_bookmark(bid_, 1000, "第1章", "摘要一", "备注一")
    rows = library.list_bookmarks(bid_)
    assert len(rows) == 1 and rows[0]["note"] == "备注一", "写入失败"
    return "id=%d" % bm


def t_update_note():
    bid_ = int(reader.book["id"])
    row = library.list_bookmarks(bid_)[0]
    library.update_bookmark_note(int(row["id"]), "改过的备注")
    assert library.list_bookmarks(bid_)[0]["note"] == "改过的备注"
    return "备注可更新"


def t_find_near():
    bid_ = int(reader.book["id"])
    assert library.find_bookmark_near(bid_, 1100) is not None, "附近查不到"
    assert library.find_bookmark_near(bid_, 99999) is None, "远距离误报"
    return "±400 字节内命中，远处不误报"


def t_delete():
    bid_ = int(reader.book["id"])
    row = library.list_bookmarks(bid_)[0]
    library.delete_bookmark(int(row["id"]))
    assert library.list_bookmarks(bid_) == []
    return "删除成功"


check("添加书签", t_add)
check("更新备注", t_update_note)
check("邻近查重", t_find_near)
check("删除书签", t_delete)

print("\n== 2. 界面联动 ==")


def t_add_via_ui():
    reader.goto_offset(5_000_000)
    app.processEvents()
    win.add_bookmark()
    app.processEvents()
    rows = library.list_bookmarks(int(reader.book["id"]))
    assert len(rows) == 1, "界面添加失败：%d 条" % len(rows)
    r = rows[0]
    assert abs(int(r["offset"]) - reader.top_offset()) < 400, "偏移不对"
    assert r["excerpt"], "摘要为空"
    assert win.side.isVisible() and win.side.currentWidget() is win.bookmarks, "没有打开书签栏"
    assert win.bookmarks.list.count() == 1
    return "书签位于 %s，摘要 %r" % (format(int(r["offset"]), ","), r["excerpt"][:16])


def t_duplicate():
    before = len(library.list_bookmarks(int(reader.book["id"])))
    win.add_bookmark()                      # 同一位置再点一次
    app.processEvents()
    after = len(library.list_bookmarks(int(reader.book["id"])))
    assert after == before, "重复添加产生了新记录：%d -> %d" % (before, after)
    return "同位置重复添加被拦下"


def t_jump():
    rows = library.list_bookmarks(int(reader.book["id"]))
    target = rows[0]
    reader.goto_offset(0)
    app.processEvents()
    win._on_bookmark_jump(int(target["offset"]))
    app.processEvents()
    assert abs(reader.top_offset() - int(target["offset"])) < 400, \
        "跳转后位置不对：%d vs %d" % (reader.top_offset(), target["offset"])
    assert reader.pg.doc.toPlainText().strip(), "跳转后正文为空"
    return "跳转到 %s" % format(int(target["offset"]), ",")


def t_panel_toggle():
    win.close_side()
    app.processEvents()
    win.toggle_bookmarks()
    app.processEvents()
    assert win.side.isVisible() and win.side.currentWidget() is win.bookmarks
    win.toggle_bookmarks()
    app.processEvents()
    assert not win.side.isVisible(), "再次切换没有收起"
    return "展开/收起正常"


def t_delete_via_ui():
    rows = library.list_bookmarks(int(reader.book["id"]))
    win.library.delete_bookmark(int(rows[0]["id"]))
    win._load_bookmarks()
    app.processEvents()
    assert library.list_bookmarks(int(reader.book["id"])) == []
    assert win.bookmarks.list.count() == 1, "空列表占位没显示"
    return "删除后面板刷新"


def t_clear_on_shelf():
    win.add_bookmark()
    app.processEvents()
    win.back_to_shelf()
    app.processEvents()
    assert win.bookmarks.list.count() == 1, "回书架后没有清空"
    win.open_book(bid)
    app.processEvents()
    win._stop_worker()
    return "回书架清空面板"


check("界面添加书签", t_add_via_ui)
check("重复添加去重", t_duplicate)
check("点击跳转", t_jump)
check("面板展开收起", t_panel_toggle)
check("删除后刷新", t_delete_via_ui)
check("换书清空", t_clear_on_shelf)

win._stop_worker()
win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
