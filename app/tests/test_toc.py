# -*- coding: utf-8 -*-
"""目录识别与章节存储测试（无界面）。"""
import os
import sys
import time
import traceback

from app.core import toc
from app.core.library import Library
from app.core.textfile import TextFile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
GBK = os.path.join(ROOT, "spike", "corpus", "gbk_20mb.txt")
TMP = os.path.join(ROOT, "build", "toc_test")
os.makedirs(TMP, exist_ok=True)

passed = failed = 0


def check(name, fn):
    global passed, failed
    t0 = time.perf_counter()
    try:
        detail = fn()
        dt = (time.perf_counter() - t0) * 1000
        print("  PASS  %-38s %7.1f ms  %s" % (name, dt, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-38s %s" % (name, e))
        traceback.print_exc()
        failed += 1


print("\n== 1. 识别 ==")

cache = {}


def t_detect_utf8():
    tf = TextFile(BIG).open()
    t0 = time.perf_counter()
    ch = toc.detect(tf)
    dt = (time.perf_counter() - t0) * 1000
    tf.close()
    assert len(ch) > 1000, "只识别到 %d 章" % len(ch)
    cache["big"] = ch
    text = toc.summary(ch)
    assert dt < 800, "识别太慢：%.0f ms（目标 < 500 ms）" % dt
    return "%s，%.0f ms" % (text, dt)


def t_offsets():
    ch = cache["big"]
    offs = [c.offset for c in ch]
    assert offs[0] == 0, "首章应从偏移 0 开始，实际 %d" % offs[0]
    assert offs == sorted(offs), "章节偏移没有升序"
    assert len(set(offs)) == len(offs), "存在重复偏移"
    size = os.path.getsize(BIG)
    assert offs[-1] < size, "偏移越界"
    return "%d 章偏移严格升序，末章 %d < %d" % (len(offs), offs[-1], size)


def t_titles():
    ch = cache["big"]
    bad = [c for c in ch if not c.title.strip() or len(c.title) > 60]
    assert not bad, "有 %d 条标题异常：%r" % (len(bad), bad[:2])
    levels = {c.level for c in ch}
    assert levels <= {1, 2, 3}, "层级异常：%r" % levels
    assert all(c.title == c.title.strip() for c in ch), "标题未去空白"
    return "标题均非空且 <= 60 字，层级 %r" % sorted(levels)


def t_gbk():
    tf = TextFile(GBK).open()
    ch = toc.detect(tf)
    tf.close()
    assert len(ch) > 300, "GBK 只识别到 %d 章" % len(ch)
    assert all(isinstance(c.title, str) and c.title for c in ch)
    return "%d 章（GBK）" % len(ch)


def t_reject():
    """不该把正文误判成章节：用一段没有章节格式的文本验证会返回空。"""
    p = os.path.join(TMP, "plain.txt")
    with open(p, "w", encoding="utf-8") as f:
        for i in range(200):
            f.write("这是一段普通的正文，没有任何章节标题，用来验证误识别率。\n")
    tf = TextFile(p).open()
    ch = toc.detect(tf)
    tf.close()
    assert ch == [], "无章节格式的文本却识别出 %d 条" % len(ch)
    return "纯正文文件正确返回空"


check("UTF-8 100MB 识别", t_detect_utf8)
check("偏移严格升序无重复", t_offsets)
check("标题与层级合法", t_titles)
check("GBK 文件识别", t_gbk)
check("纯正文不误判", t_reject)

print("\n== 2. 存储 ==")

db = os.path.join(TMP, "toc.db")
for f in ("toc.db", "toc.db-wal", "toc.db-shm"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass
lib = Library(db)
bid = lib.add_file(BIG)
assert bid


def t_store():
    n = lib.replace_chapters(bid, cache["big"])
    rows = lib.list_chapters(bid)
    assert n == len(rows) == len(cache["big"]), "%d / %d / %d" % (n, len(rows), len(cache["big"]))
    assert rows[0]["start_off"] == 0
    assert rows[0]["title"] == cache["big"][0].title
    assert [r["idx"] for r in rows] == list(range(len(rows))), "idx 不连续"
    return "写入并读回 %d 条" % len(rows)


def t_idempotent():
    n1 = lib.replace_chapters(bid, cache["big"])
    n2 = lib.replace_chapters(bid, cache["big"])
    rows = lib.list_chapters(bid)
    assert n1 == n2 == len(rows), "重复写入产生了重复行：%d" % len(rows)
    return "重复写入不产生重复行"


def t_ensure_cached():
    # 先把章节清掉，否则两次都是缓存命中，测不出「首次识别 / 二次缓存」的差别
    lib.conn.execute("DELETE FROM chapter WHERE book_id = ?", (bid,))
    lib.conn.execute("UPDATE book SET chapter_count = NULL WHERE id = ?", (bid,))
    lib.conn.commit()
    assert lib.list_chapters(bid) == [], "清空失败"

    book = lib.get_book(bid)
    t0 = time.perf_counter()
    a = lib.ensure_chapters(book)
    first = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    b = lib.ensure_chapters(book)
    second = (time.perf_counter() - t0) * 1000

    assert len(a) == len(b) > 1000, "识别结果异常：%d / %d" % (len(a), len(b))
    assert second * 5 < first, "缓存没生效：首次 %.1f ms，二次 %.1f ms" % (first, second)
    return "首次识别 %.1f ms -> 缓存 %.1f ms（%.0f 倍）" % (first, second, first / max(second, 0.01))


check("章节写入与读回", t_store)
check("重复写入幂等", t_idempotent)
check("ensure_chapters 走缓存", t_ensure_cached)

print("\n== 3. 章节定位（二分）==")


def t_locate():
    rows = lib.list_chapters(bid)
    offs = [r["start_off"] for r in rows]
    from bisect import bisect_right
    # 随便挑几个偏移，验证落在正确的章节区间里
    for probe in (0, 5000, 1_000_000, 50_000_000, offs[-1] + 100):
        i = bisect_right(offs, probe) - 1
        assert 0 <= i < len(rows), "定位失败 probe=%d" % probe
        start = rows[i]["start_off"]
        end = rows[i + 1]["start_off"] if i + 1 < len(rows) else os.path.getsize(BIG)
        assert start <= probe < end, "probe=%d 落在 %d..%d 之外" % (probe, start, end)
    return "5 个探针均命中正确区间"


check("偏移->章节区间", t_locate)

lib.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
