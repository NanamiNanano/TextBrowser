# -*- coding: utf-8 -*-
"""核心层无头冒烟测试：编码识别、mmap 索引、分页、书架存储。

用法: python -m app.tests.smoke_core
"""
import os
import sys
import tempfile
import time
import traceback

from PySide6.QtWidgets import QApplication

from app.core.encoding import detect
from app.core.library import Library
from app.core.paginate import Layout, Paginator
from app.core.settings import Settings
from app.core.textfile import TextFile, probe_encoding

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CORPUS = os.path.join(ROOT, "spike", "corpus")
BIG = os.path.join(CORPUS, "big_100mb.txt")
GBK = os.path.join(CORPUS, "gbk_20mb.txt")

app = QApplication.instance() or QApplication([])

passed = failed = 0


def check(name, fn):
    global passed, failed
    t0 = time.perf_counter()
    try:
        detail = fn()
        dt = (time.perf_counter() - t0) * 1000
        print("  PASS  %-42s %7.1f ms  %s" % (name, dt, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-42s %s" % (name, e))
        traceback.print_exc()
        failed += 1


print("\n== 1. 编码识别 ==")


def t_detect_utf8():
    with open(BIG, "rb") as f:
        head = f.read(256 * 1024)
    enc, conf = detect(head)
    assert enc == "utf-8", "期望 utf-8，实际 %s" % enc
    return "%s conf=%.2f" % (enc, conf)


def t_detect_gbk():
    with open(GBK, "rb") as f:
        head = f.read(256 * 1024)
    enc, conf = detect(head)
    assert enc in ("gb18030", "gbk"), "期望 gb18030，实际 %s" % enc
    return "%s conf=%.2f" % (enc, conf)


def t_detect_bom():
    enc, _ = detect(b"\xef\xbb\xbfhello")
    assert enc == "utf-8"
    enc2, _ = detect(b"\xff\xfeh\x00i\x00")
    assert enc2 == "utf-16-le", enc2
    return "BOM 识别正确"


check("UTF-8 100MB 采样", t_detect_utf8)
check("GBK 20MB 采样", t_detect_gbk)
check("BOM 优先", t_detect_bom)

print("\n== 2. TextFile / mmap ==")

tf = TextFile(BIG)


def t_open():
    tf.open()
    assert tf.size > 100 * 1024 * 1024 - 1
    return "encoding=%s newline=%r" % (tf.encoding, tf.newline)


def t_index():
    t0 = time.perf_counter()
    n = tf.build_index()
    dt = (time.perf_counter() - t0) * 1000
    assert n > 100000, n
    return "%d 行 / %.1f ms" % (n, dt)


def t_line_count():
    assert tf.line_count == 288250 or tf.line_count > 100000
    return "%d 行" % tf.line_count


def t_read_window():
    s = tf.read_window(0, 500)      # 500 字节 ≈ 200 个汉字字符
    assert "第1" in s, s[:40]
    assert len(s) > 100, len(s)
    return "%d 字: %s" % (len(s), s.split("\n")[0][:16])


def t_binary_search():
    mid = tf.size // 2
    line = tf.line_of_offset(mid)
    start = tf.line_start(line)
    assert start <= mid
    return "offset %d -> 行 %d" % (mid, line)


check("打开 + 采样", t_open)
check("建行索引", t_index)
check("行数", t_line_count)
check("窗口读取", t_read_window)
check("偏移→行二分", t_binary_search)

print("\n== 3. 分页引擎 ==")

layout = Layout(width=780, height=900, font_family="Microsoft YaHei",
                font_px=20, line_height=1.8, margin_h=0, margin_v=0)
pg = Paginator(tf, layout)


def t_first_page():
    p = pg.layout_page(0)
    assert p.chars > 100, p.chars
    assert p.end > p.start
    return "%d 字 / %d..%d 字节" % (p.chars, p.start, p.end)


def t_page_turn_speed():
    off = 0
    n = 50
    t0 = time.perf_counter()
    for _ in range(n):
        p = pg.layout_page(off)
        if p.is_empty:
            break
        off = p.end
    dt = (time.perf_counter() - t0) * 1000
    return "%d 页 / %.1f ms 均值 %.2f ms" % (n, dt, dt / n)


def t_contiguous():
    """连续翻页必须严格前进且不丢字。"""
    off = 0
    ends = []
    for _ in range(20):
        p = pg.layout_page(off)
        assert p.start == off, "页起点不连续: %d != %d" % (p.start, off)
        assert p.end > p.start, "页未前进"
        ends.append(p.end)
        off = p.end
    assert ends == sorted(ends) and len(set(ends)) == len(ends)
    return "20 页连续，末偏移 %d" % off


def t_font_size_change():
    out = []
    for px in (14, 20, 28, 40):
        l2 = Layout(780, 900, "Microsoft YaHei", px, 1.8)
        p2 = Paginator(tf, l2).layout_page(0)
        out.append("%dpx=%d字" % (px, p2.chars))
    return " ".join(out)


def t_char_count():
    n = tf.char_count()
    assert n > 30_000_000, n
    return "%.1f M 字符" % (n / 1e6)


check("首页排版", t_first_page)
check("连续翻页吞吐", t_page_turn_speed)
check("页边界连续性", t_contiguous)
check("改字号重新分页", t_font_size_change)
check("全文字符数", t_char_count)

print("\n== 4. 书架存储 ==")

tmpdb = os.path.join(tempfile.gettempdir(), "tb_smoke_%d.db" % os.getpid())
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(tmpdb + suffix)
    except OSError:
        pass
lib = Library(tmpdb)


def t_add_book():
    bid = lib.add_file(BIG)
    assert bid, "导入失败"
    again = lib.add_file(BIG)
    assert again == bid, "重复导入产生了新记录: %s vs %s" % (bid, again)
    return "book_id=%d（重复导入去重正常）" % bid


def t_list():
    books = lib.list_books()
    assert len(books) == 1, len(books)
    b = books[0]
    assert b["format"] == "txt"
    assert b["encoding"] == "utf-8"
    return "%s | %s | %.1f MB" % (b["title"], b["encoding"], b["file_size"] / 1048576)


def t_progress():
    bid = lib.list_books()[0]["id"]
    lib.save_progress(bid, 12345678, 11.8)
    p = lib.get_progress(bid)
    assert p["offset"] == 12345678, p
    lib.save_progress(bid, 23456789, 22.4)
    p = lib.get_progress(bid)
    assert p["offset"] == 23456789, p
    return "offset 覆盖写入正常 -> %d" % p["offset"]


def t_bookmark():
    bid = lib.list_books()[0]["id"]
    bm = lib.add_bookmark(bid, 999, "第1章 夜色渐深", "他推开门……", "测试备注")
    rows = lib.list_bookmarks(bid)
    assert len(rows) == 1 and rows[0]["note"] == "测试备注"
    lib.delete_bookmark(bm)
    assert len(lib.list_bookmarks(bid)) == 0
    return "增删查正常"


def t_settings():
    sp = os.path.join(tempfile.gettempdir(), "tb_settings_%d.json" % os.getpid())
    s = Settings(sp)
    assert s.get("appearance.fontSize") == 20
    s.set("appearance.fontSize", 26)
    assert s.save()
    s2 = Settings(sp)
    assert s2.get("appearance.fontSize") == 26, "设置未持久化"
    s2.set("appearance.bgColor", "#000000")
    s2.save()
    s3 = Settings(sp)
    assert s3.get("appearance.bgColor") == "#000000"
    os.remove(sp)
    return "读写/持久化正常"


check("导入 + 去重", t_add_book)
check("书架列表", t_list)
check("进度保存", t_progress)
check("书签增删", t_bookmark)
check("设置持久化", t_settings)

lib.close()
tf.close()
for suffix in ("", "-wal", "-shm"):
    try:
        os.remove(tmpdb + suffix)
    except OSError:
        pass

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
