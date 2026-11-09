# -*- coding: utf-8 -*-
"""阅读视图回归测试。

重点是「拖窗口后正文消失」这个 bug：resizeEvent 里如果只重建 Paginator 而不
重排，QTextDocument 是空的，画面就是白的，直到翻页才恢复。所以这里的断言不能
只看 reader.page.text（那是旧对象，仍有内容），必须看 pg.doc 里真正的内容。
"""
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
GBK = os.path.join(ROOT, "spike", "corpus", "gbk_20mb.txt")
TMP = os.path.join(ROOT, "build", "reader_test")

app = QApplication.instance() or QApplication([])

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-40s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-40s %s" % (name, e))
        traceback.print_exc()
        failed += 1


def doc_text(reader) -> str:
    """真正被绘制出来的内容（不是 page 对象上的缓存）。"""
    if reader.pg is None:
        return ""
    return reader.pg.doc.toPlainText()


def page_text_of(reader) -> str:
    return reader.page.text if reader.page else ""


def assert_visible(reader, why=""):
    txt = doc_text(reader)
    assert txt.strip(), "文档是空的（会显示白屏）%s" % why
    assert reader.page is not None and reader.page.text.strip(), "page 对象为空 %s" % why


# ---------------------------------------------------------------- 准备
os.makedirs(TMP, exist_ok=True)
for f in ("t.db", "t.db-wal", "t.db-shm"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass

settings = Settings(os.path.join(TMP, "settings.json"))
library = Library(os.path.join(TMP, "t.db"))
bid = library.add_file(BIG)
assert bid, "语料缺失：%s（先用 spike/gen_corpus.py 生成）" % BIG

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()
win.open_book(bid)
app.processEvents()

reader = win.reader
assert reader.tf is not None, "文档没有打开"

print("\n== 1. 打开后正常 ==")


def t_open():
    assert_visible(reader)
    return "%d 字 / 偏移 %d" % (reader.page.chars, reader.page.start)


check("打开后有内容", t_open)

print("\n== 2. 拖宽窗口（正文栏被 maxContentWidth 卡住，正是 bug 触发条件）==")


def t_wider():
    before_start = reader.page.start
    before_doc = doc_text(reader)
    for w in (1200, 1400, 1600):
        win.resize(w, 780)
        app.processEvents()
        assert_visible(reader, "(窗口宽 %d)" % w)
    assert reader.page.start == before_start, "位置变了：%d -> %d" % (before_start, reader.page.start)
    assert doc_text(reader) == before_doc, "重排后内容不一致（不该重排）"
    return "1200/1400/1600 宽均正常，位置未变"


def t_narrower():
    for w in (860, 760, 700):
        win.resize(w, 780)
        app.processEvents()
        assert_visible(reader, "(窗口宽 %d)" % w)
    return "窄窗口重排正常"


def t_taller():
    for h in (900, 620, 800):
        win.resize(1120, h)
        app.processEvents()
        assert_visible(reader, "(窗口高 %d)" % h)
    return "高度变化重排正常"


check("拖宽不变白（核心回归）", t_wider)
check("拖窄重排正常", t_narrower)
check("高度变化正常", t_taller)

print("\n== 3. 改外观后仍可读 ==")


def t_font():
    win.resize(1120, 780)
    app.processEvents()
    before = reader.page.start
    for size in (26, 14, 20):
        settings.set("appearance.fontSize", size)
        reader.apply_appearance()
        app.processEvents()
        assert_visible(reader, "(字号 %d)" % size)
        assert reader.page.start == before, "改字号后位置漂移"
    return "字号 26/14/20 切换正常，偏移不变"


def t_line_height():
    settings.set("appearance.lineHeight", 2.2)
    reader.apply_appearance()
    app.processEvents()
    assert_visible(reader, "(行距 2.2)")
    settings.set("appearance.lineHeight", 1.8)
    reader.apply_appearance()
    app.processEvents()
    assert_visible(reader)
    return "行距切换正常"


check("改字号后不白屏不漂移", t_font)
check("改行距后正常", t_line_height)

print("\n== 4. 缩放后翻页链路仍通 ==")


def t_turn():
    win.resize(1000, 700)
    app.processEvents()
    start0 = reader.page.start
    assert reader.next_page(), "下一页失败"
    app.processEvents()
    assert_visible(reader)
    assert reader.page.start > start0, "没有前进"
    assert reader.prev_page(), "上一页失败"
    app.processEvents()
    assert_visible(reader)
    assert reader.page.start == start0, "上一页没回到原位：%d != %d" % (reader.page.start, start0)
    return "缩放后 下一页/上一页 正常且对齐"


check("缩放后翻页与回退", t_turn)

print("\n== 5. 连续缩放压力（模拟用户拖动窗口边缘）==")


def t_stress():
    for i in range(12):
        w = 720 + (i % 6) * 110
        h = 560 + (i % 4) * 90
        win.resize(w, h)
        app.processEvents()
        assert_visible(reader, "(第 %d 次 %dx%d)" % (i + 1, w, h))
    return "12 次随机缩放均正常"


check("连续缩放不出空白", t_stress)

print("\n== 6. GBK 文件同样正常 ==")


def t_gbk():
    b2 = library.add_file(GBK)
    assert b2, "GBK 语料缺失"
    win.open_book(b2)
    app.processEvents()
    assert_visible(reader, "(GBK)")
    for w in (1400, 760):
        win.resize(w, 780)
        app.processEvents()
        assert_visible(reader, "(GBK 宽 %d)" % w)
    return "GBK 打开 + 缩放正常"


check("GBK 文件缩放正常", t_gbk)

print("\n== 7. 目录侧栏 ==")


def t_toc_load():
    books = [b for b in library.list_books() if b["id"] == bid]
    win.open_book(bid)
    app.processEvents()
    win._load_toc()                      # 直接调用，绕过 QTimer
    app.processEvents()
    assert reader._chap_offsets, "章节没加载进阅读视图"
    assert win.toc.list.count() > 1000, "侧栏条目太少：%d" % win.toc.list.count()
    return "%d 章已载入" % len(reader._chap_offsets)


def t_toc_locate():
    chapters = library.list_chapters(bid)
    target = chapters[100]
    reader.goto_offset(int(target["start_off"]))
    app.processEvents()
    assert reader.current_chapter_title() == target["title"], \
        "定位到第 101 章后当前章节是 %r，期望 %r" % (
            reader.current_chapter_title(), target["title"])
    assert_visible(reader, "(跳章后)")
    return "跳到「%s」并正确高亮" % target["title"][:16]


def t_toc_toggle():
    win.toggle_toc()
    app.processEvents()
    assert win.toc.isVisible(), "Ctrl+T 没有展开目录"
    win.toc.highlight_offset(reader.page.start)
    app.processEvents()
    row = win.toc.list.currentRow()
    assert row > 0, "侧栏没有选中当前章节，row=%d" % row
    win.toggle_toc()
    app.processEvents()
    assert not win.toc.isVisible(), "再次 Ctrl+T 没有收起"
    return "展开/收起/高亮正常（row=%d）" % row


def t_toc_jump():
    chapters = library.list_chapters(bid)
    target = chapters[250]
    win._on_toc_jump(int(target["start_off"]))
    app.processEvents()
    assert reader.page.start == int(target["start_off"]), "跳转没落到章节起点"
    assert_visible(reader, "(侧栏跳转后)")
    return "侧栏跳转到「%s」" % target["title"][:16]


check("加载目录", t_toc_load)
check("按章节定位", t_toc_locate)
check("侧栏展开/收起", t_toc_toggle)
check("侧栏跳转", t_toc_jump)

print("\n== 8. 搜索与页内高亮 ==")


def t_search_panel():
    win.toggle_search()
    app.processEvents()
    assert win.side.isVisible(), "搜索侧栏没有展开"
    assert win.side.currentWidget() is win.search, "侧栏没有切到搜索页"
    win.search.input.setText("长夜将至")
    win.search.run_search()
    app.processEvents()
    hits = win.search.current_hits()
    assert hits, "没搜到「长夜将至」"
    assert win.search.list.count() > 0, "结果列表是空的"
    return "%s，列表 %d 行" % (win.search.lbl_status.text(), win.search.list.count())


def t_search_jump():
    hits = win.search.current_hits()
    target = hits[min(5, len(hits) - 1)]
    win._on_search_jump(target.offset, target.length)
    app.processEvents()
    assert reader.page.start <= target.offset < reader.page.end, \
        "跳转后命中不在当前页内：%d 不在 %d..%d" % (target.offset, reader.page.start, reader.page.end)
    assert_visible(reader, "(搜索跳转后)")
    return "跳到偏移 %d（页内）" % target.offset


def t_highlight():
    ranges = getattr(reader.pg, "_highlights", [])
    assert ranges, "命中区间上的高亮一个都没有"
    kw = "长夜将至"
    texts = [reader.page.text[s:e] for s, e in ranges]
    assert kw in texts, "高亮区间取出来的文字不是关键词：%r" % texts[:3]
    # 当前命中应使用更重的底色（被记在 _highlight_current 里）
    assert reader.pg._highlight_current is not None, "当前命中没有单独标记"
    return "%d 处高亮，其中当前命中已强调" % len(ranges)


def t_highlight_cleared():
    chapters = library.list_chapters(bid)
    win._on_toc_jump(int(chapters[3]["start_off"]))
    app.processEvents()
    # 跳到没有命中的章节后，高亮应该消失（否则整本书都挂着色块）
    ranges = getattr(reader.pg, "_highlights", [])
    assert not ranges, "离开命中区后仍有 %d 处高亮" % len(ranges)
    assert_visible(reader, "(离开命中区后)")
    return "离开命中区后高亮正确清除"


check("搜索面板出结果", t_search_panel)
check("点击结果跳转", t_search_jump)
check("页内高亮命中", t_highlight)
check("离开命中区清除高亮", t_highlight_cleared)

win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
