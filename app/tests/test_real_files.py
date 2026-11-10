# -*- coding: utf-8 -*-
"""真实文件的端到端测试：12 MB 中文小说 TXT + 10 MB EPUB。

用参考文本文件夹里的真实文件跑，覆盖合成语料测不到的情况：
  * TXT：标题行 + 缩进重复标题、章节名以括号结尾、正文里的「99.7%」数字行
  * EPUB：EPUB2 + ncx 目录、1587 个 spine 文件、封面页
"""
import os
import sys
import time
import traceback

from PySide6.QtWidgets import QApplication

from app.core import epub, toc
from app.core.library import Library
from app.core.search import search
from app.core.settings import Settings
from app.core.textfile import TextFile
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
REF = os.path.join(ROOT, "参考文本")
TXT = os.path.join(REF, "《没钱修什么仙？》作者：熊狼狗.txt")
EPUB = os.path.join(REF, "黎明之剑.epub")
TMP = os.path.join(ROOT, "build", "real_test")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])

passed = failed = skipped = 0


def check(name, fn):
    global passed, failed, skipped
    t0 = time.perf_counter()
    try:
        detail = fn()
        dt = (time.perf_counter() - t0) * 1000
        print("  PASS  %-34s %7.1f ms  %s" % (name, dt, detail or ""))
        passed += 1
    except AssertionError as e:
        print("  FAIL  %-34s %s" % (name, e))
        failed += 1
    except Exception as e:
        print("  FAIL  %-34s %s" % (name, e))
        traceback.print_exc()
        failed += 1


if not os.path.exists(TXT) or not os.path.exists(EPUB):
    print("跳过：参考文本缺失\n  需要 %s\n  需要 %s" % (TXT, EPUB))
    sys.exit(0)

print("\n== 1. 真实 TXT（12 MB 小说）==")


def t_txt_detect():
    tf = TextFile(TXT).open()
    try:
        ch = toc.detect(tf)
    finally:
        tf.close()
    assert len(ch) > 900, "只识别到 %d 章" % len(ch)
    import re
    nums = [int(m.group(1)) for c in ch
            for m in [re.match(r"^第\s*(\d+)\s*章", c.title)] if m]
    missing = sorted(set(range(1, max(nums) + 1)) - set(nums))
    assert not missing, "漏了 %d 章，例如 %r" % (len(missing), missing[:8])
    return "%d 章，1..%d 无缺失" % (len(ch), max(nums))


def t_txt_no_false():
    """数字行（99.7% / 14.99）不能被当章节；README 里的坑。"""
    tf = TextFile(TXT).open()
    try:
        ch = toc.detect(tf)
    finally:
        tf.close()
    bad = [c.title for c in ch if c.level != 2]
    assert not bad, "出现了 %d 个非章节条目：%r" % (len(bad), bad[:6])
    return "全部为 2 级章节，无数字行误判"


def t_txt_indent_dup():
    """标题行 + 缩进重复标题 的格式不能产生「相邻且几乎同位置」的重复章节。

    注意：源文件本身在第 694 章后重复了一整章（相隔 20 KB），那是内容重复，
    不是识别问题，所以这里只针对「相距很近的重复」（缩进重复标题的产物）。
    """
    tf = TextFile(TXT).open()
    try:
        ch = toc.detect(tf)
    finally:
        tf.close()
    close_dups = [ch[i].title for i in range(len(ch) - 1)
                  if ch[i].title == ch[i + 1].title
                  and (ch[i + 1].offset - ch[i].offset) < 300]
    assert not close_dups, "存在 %d 组紧邻重复章节：%r" % (len(close_dups), close_dups[:3])
    return "无紧邻重复（源文件自带的跨章重复不计）"


def t_txt_speed():
    tf = TextFile(TXT).open()
    try:
        t0 = time.perf_counter()
        toc.detect(tf)
        dt = (time.perf_counter() - t0) * 1000
    finally:
        tf.close()
    assert dt < 600, "识别太慢：%.0f ms" % dt
    return "识别 %.0f ms" % dt


check("识别完整无缺失", t_txt_detect)
check("无误判条目", t_txt_no_false)
check("重复标题去重", t_txt_indent_dup)
check("识别速度", t_txt_speed)

print("\n== 2. 真实 EPUB（10 MB，1587 个文件）==")

# 清理旧缓存
for name in os.listdir(TMP):
    if name.startswith("real") and name.endswith((".db", ".db-wal", ".db-shm")):
        try:
            os.remove(os.path.join(TMP, name))
        except OSError:
            pass
settings = Settings(os.path.join(TMP, "s.json"))
library = Library(os.path.join(TMP, "real.db"))
bid = library.add_file(EPUB)


def t_epub_meta():
    book = library.get_book(bid)
    assert book["format"] == "epub", "格式识别错误：%s" % book["format"]
    assert book["title"] == "黎明之剑", "书名应取自 OPF，实际 %r" % book["title"]
    assert book["author"] == "远瞳", "作者应取自 OPF，实际 %r" % book["author"]
    return "书名/作者来自 OPF：%s / %s" % (book["title"], book["author"])


def t_epub_convert():
    """直接转换到临时路径，不动真正的缓存——真正的缓存在打开时才生成。"""
    probe = library.epub_cache_path(bid) + ".probe"
    t0 = time.perf_counter()
    result = epub.convert(EPUB, probe)
    dt = time.perf_counter() - t0
    try:
        assert os.path.exists(probe), "缓存没有生成"
        assert len(result.chapters) > 1000, "只解析出 %d 章" % len(result.chapters)
        assert dt < 10, "转换太慢：%.1f s" % dt
        return "%d 章，%.1f MB，%.2f s" % (
            len(result.chapters), os.path.getsize(probe) / 1048576, dt)
    finally:
        try:
            os.remove(probe)
        except OSError:
            pass


def t_epub_chapters():
    cache = library.epub_cache_path(bid)
    result = epub.convert(EPUB, cache + ".again")
    try:
        titles = [c.title for c in result.chapters]
        assert titles[0] == "封面", "首条应为封面，实际 %r" % titles[0]
        assert "第一章" in titles[1], "第二个条目应是第一章，实际 %r" % titles[1]
        assert any("完本感言" in t for t in titles), "缺少完本感言"
        assert len(set(titles)) > len(titles) * 0.95, "标题重复率过高"
        return "首=%r 次=%r 末=%r" % (titles[0], titles[1], titles[-1])
    finally:
        try:
            os.remove(cache + ".again")
        except OSError:
            pass


check("EPUB 元数据", t_epub_meta)
check("EPUB 转换", t_epub_convert)
check("EPUB 章节标题", t_epub_chapters)

print("\n== 3. 在阅读器里打开 EPUB ==")

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()


def t_open():
    t0 = time.perf_counter()
    win.open_book(bid)
    app.processEvents()
    dt = time.perf_counter() - t0
    r = win.reader
    assert r.tf is not None, "没有打开文档"
    assert r.pg.doc.toPlainText().strip(), "正文为空"
    assert r.tf.path.endswith(".txt"), "应该读转换后的缓存文件，实际 %s" % r.tf.path
    assert dt < 15, "首次打开太慢：%.1f s" % dt
    return "打开耗时 %.2f s，读的是缓存" % dt


def t_reopen_cached():
    """第二次打开应直接走缓存，不再转换。"""
    from app.core import epub as epub_mod
    original = epub_mod.convert
    called = {"n": 0}

    def spy(*a, **kw):
        called["n"] += 1
        return original(*a, **kw)

    epub_mod.convert = spy
    try:
        t0 = time.perf_counter()
        win.back_to_shelf()
        win.open_book(bid)
        app.processEvents()
        dt = time.perf_counter() - t0
    finally:
        epub_mod.convert = original
    assert called["n"] == 0, "第二次打开又重新转换了"
    assert dt < 3, "二次打开太慢：%.2f s" % dt
    return "二次打开 %.2f s，未重新转换" % dt


def t_toc():
    win._load_toc()
    w = win._chapter_worker
    if w is not None and w.isRunning():
        w.wait(20000)
    app.processEvents()
    ch = library.list_chapters(bid)
    assert len(ch) > 1000, "章节表只有 %d 条" % len(ch)
    assert win.toc.list.count() > 1000, "侧栏条目太少"
    target = ch[100]
    win._on_toc_jump(int(target["start_off"]))
    app.processEvents()
    assert win.reader.current_chapter_title() == target["title"], \
        "跳转后章节不对：%r vs %r" % (win.reader.current_chapter_title(), target["title"])
    return "跳转到「%s」" % target["title"][:20]


def t_search():
    hits = search(win.reader.tf, "高文")
    assert hits, "在 EPUB 缓存里没搜到主角名"
    return "搜索「高文」命中 %d 条" % len(hits)


def t_read_pages():
    """连续翻 20 页，确认 EPUB 缓存的分页稳定。"""
    win.goto_first_page() if hasattr(win, "goto_first_page") else win.reader.goto_offset(0)
    app.processEvents()
    last = -1
    for _ in range(20):
        assert win.reader.next_page(), "翻页中断"
        app.processEvents()
        assert win.reader.pg.doc.toPlainText().strip(), "出现空白页"
        assert win.reader.page.start > last, "偏移没有前进"
        last = win.reader.page.start
    return "连续 20 页均正常"


check("打开 EPUB", t_open)
check("二次打开走缓存", t_reopen_cached)
check("目录与跳转", t_toc)
check("全文搜索", t_search)
check("连续翻页", t_read_pages)

win._stop_worker()
win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
