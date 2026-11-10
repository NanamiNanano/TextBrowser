# -*- coding: utf-8 -*-
"""阅读模式（分页 / 滚动）与页码估算的测试。"""
import os
import sys
import traceback

from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "modes_test")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-38s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-38s %s" % (name, e))
        traceback.print_exc()
        failed += 1


def doc_text(reader) -> str:
    return reader.pg.doc.toPlainText() if reader.pg else ""


def assert_visible(reader, why=""):
    assert doc_text(reader).strip(), "文档是空的 %s" % why
    assert reader.page.text.strip(), "page 为空 %s" % why


for f in ("m.db", "m.db-wal", "m.db-shm"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass

settings = Settings(os.path.join(TMP, "settings.json"))
settings.set("reading.mode", "paginate")
library = Library(os.path.join(TMP, "m.db"))
bid = library.add_file(BIG)
assert bid, "语料缺失"

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()
win.open_book(bid)
app.processEvents()
reader = win.reader

print("\n== 1. 页码估算 ==")


def t_total():
    total = reader.total_pages()
    assert total > 1000, "全书页数估算异常：%d" % total
    assert reader.page_number() == 1, "起始页码应为 1，实际 %d" % reader.page_number()
    return "全书约 %s 页，当前第 1 页" % format(total, ",")


def t_advance():
    first = reader.page_number()
    for _ in range(10):
        reader.next_page()
    app.processEvents()
    later = reader.page_number()
    assert later > first, "翻了 10 页页码没变：%d -> %d" % (first, later)
    assert later - first <= 12, "页码跳得太快：%d -> %d" % (first, later)
    return "第 %d 页 -> 第 %d 页（翻了 10 页）" % (first, later)


def t_jump_middle():
    total = reader.total_pages()
    reader.goto_offset(BIG_SIZE // 2)
    app.processEvents()
    pn = reader.page_number()
    ratio = pn / total
    assert 0.42 < ratio < 0.58, "跳到 50%% 处却算成第 %d/%d 页（占比 %.2f）" % (pn, total, ratio)
    return "跳到 50%% -> 第 %d / 约 %d 页（占比 %.2f）" % (pn, total, ratio)


def t_stable():
    """同一位置反复取页码应稳定，不随翻页次数漂移。"""
    reader.goto_offset(0)
    app.processEvents()
    a = reader.page_number()
    for _ in range(5):
        reader.next_page()
    reader.goto_offset(0)
    app.processEvents()
    b = reader.page_number()
    assert a == b == 1, "回到开头页码不稳定：%d / %d" % (a, b)
    return "回到开头页码仍为 1"


BIG_SIZE = os.path.getsize(BIG)
check("全书页数估算", t_total)
check("翻页后页码前进", t_advance)
check("跳 50% 页码接近一半", t_jump_middle)
check("页码跨会话稳定", t_stable)

print("\n== 2. 滚动模式 ==")


def t_switch():
    reader.goto_offset(0)
    app.processEvents()
    before = reader.top_offset()
    reader.set_mode("scroll")
    app.processEvents()
    assert reader.is_scroll_mode(), "没切到滚动模式"
    assert_visible(reader, "(切到滚动后)")
    assert abs(reader.top_offset() - before) < 2000, "切换后位置漂移过大"
    return "已切换到滚动，位置保持"


def t_scroll_down():
    before = reader.top_offset()
    y0 = reader._scroll_y
    for _ in range(6):
        reader.scroll_by(300)
        app.processEvents()
    after = reader.top_offset()
    assert after > before, "向下滚动后偏移没有前进：%d -> %d" % (before, after)
    assert_visible(reader, "(下滚后)")
    return "偏移 %d -> %d（滚动 %d -> %d px）" % (before, after, y0, reader._scroll_y)


def t_scroll_up():
    before = reader.top_offset()
    for _ in range(6):
        reader.scroll_by(-300)
        app.processEvents()
    after = reader.top_offset()
    assert after < before, "向上滚动后偏移没有回退：%d -> %d" % (before, after)
    assert_visible(reader, "(上滚后)")
    return "偏移 %d -> %d" % (before, after)


def t_screen_keys():
    before = reader.top_offset()
    assert reader.next_page(), "滚动模式下 E 无效"
    app.processEvents()
    mid = reader.top_offset()
    assert mid > before, "E 之后没有前进"
    assert reader.prev_page(), "滚动模式下 Q 无效"
    app.processEvents()
    back = reader.top_offset()
    assert back < mid, "Q 之后没有回退"
    return "E: %d->%d，Q: ->%d" % (before, mid, back)


def t_scroll_bottom():
    """滚到接近文件末尾不应崩，也不应越界。"""
    reader.goto_offset(BIG_SIZE - 3000)
    app.processEvents()
    for _ in range(20):
        reader.scroll_by(400)
        app.processEvents()
    assert_visible(reader, "(末尾)")
    assert reader.top_offset() < BIG_SIZE, "偏移越界"
    return "末尾滚动正常，偏移 %d < %d" % (reader.top_offset(), BIG_SIZE)


def t_back_to_paginate():
    reader.goto_offset(0)
    app.processEvents()
    reader.set_mode("scroll")
    app.processEvents()
    for _ in range(8):
        reader.scroll_by(400)
    app.processEvents()
    offset_scroll = reader.top_offset()
    reader.set_mode("paginate")
    app.processEvents()
    offset_page = reader.top_offset()
    assert not reader.is_scroll_mode()
    assert_visible(reader, "(切回分页后)")
    assert abs(offset_page - offset_scroll) < 4000, \
        "切回分页后位置漂移过大：%d vs %d" % (offset_page, offset_scroll)
    return "滚动 %d -> 分页 %d（页面起点对齐）" % (offset_scroll, offset_page)


def t_scroll_resize():
    reader.set_mode("scroll")
    app.processEvents()
    for w, h in ((1200, 800), (760, 620), (1400, 900)):
        win.resize(w, h)
        app.processEvents()
        assert_visible(reader, "(滚动模式 %dx%d)" % (w, h))
    return "滚动模式下三次缩放均正常"


def t_mode_persist():
    reader.set_mode("scroll")
    saved = settings.get("reading.mode")
    settings.save()
    reloaded = Settings(os.path.join(TMP, "settings.json"))
    assert reloaded.get("reading.mode") == "scroll", "模式没持久化"
    reader.set_mode("paginate")
    return "模式写入配置：%s" % saved


check("切换模式保持位置", t_switch)
check("向下滚动", t_scroll_down)
check("向上滚动", t_scroll_up)
check("滚动模式 Q/E 整屏", t_screen_keys)
check("滚到文件末尾", t_scroll_bottom)
check("切回分页位置对齐", t_back_to_paginate)
check("滚动模式缩放", t_scroll_resize)
check("模式持久化", t_mode_persist)

print("\n== 3. 滚动模式下的进度与高亮 ==")


def t_scroll_progress():
    reader.set_mode("scroll")
    reader.goto_offset(BIG_SIZE // 3)
    app.processEvents()
    reader.scroll_by(500)
    app.processEvents()
    reader._save_progress(force=True)
    prog = library.get_progress(bid)
    assert prog["offset"] > BIG_SIZE // 3 - 1000, "进度没记录滚动位置：%d" % prog["offset"]
    assert 25 < prog["percent"] < 45, "百分比异常：%.1f" % prog["percent"]
    return "进度 %d（%.1f%%）" % (prog["offset"], prog["percent"])


def t_scroll_pages():
    """滚动模式下也要有页码：一块按 2.4 屏折算，否则页码会小 2.4 倍。"""
    total = reader.total_pages()
    pn = reader.page_number()
    assert total > 1000, "滚动模式下没有全书页数：%d" % total
    assert 1 <= pn <= total, "页码越界：%d / %d" % (pn, total)
    ratio = pn / total
    assert 0.25 < ratio < 0.45, "滚到 33%% 处页码占比异常：%.2f" % ratio
    return "第 %d / 约 %d 页（占比 %.2f）" % (pn, total, ratio)


def t_scroll_highlight():
    from app.core.search import search
    hits = search(reader.tf, "长夜将至", limit=200)
    reader.set_search_hits([(h.offset, h.length) for h in hits])
    reader.goto_offset(hits[3].offset, align_line=True)
    app.processEvents()
    ranges = getattr(reader.pg, "_highlights", [])
    assert ranges, "滚动模式下没有高亮"
    assert_visible(reader, "(滚动高亮)")
    reader.clear_search_hits()
    reader.set_mode("paginate")
    return "滚动模式下命中 %d 处高亮" % len(ranges)


check("滚动模式进度保存", t_scroll_progress)
check("滚动模式页码", t_scroll_pages)
check("滚动模式搜索高亮", t_scroll_highlight)

win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
