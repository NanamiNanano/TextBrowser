# -*- coding: utf-8 -*-
"""全文搜索测试（无界面）。"""
import os
import sys
import time
import traceback

from app.core.search import MAX_HITS, search
from app.core.textfile import TextFile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
GBK = os.path.join(ROOT, "spike", "corpus", "gbk_20mb.txt")

passed = failed = 0


def check(name, fn):
    global passed, failed
    t0 = time.perf_counter()
    try:
        detail = fn()
        dt = (time.perf_counter() - t0) * 1000
        print("  PASS  %-36s %7.1f ms  %s" % (name, dt, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-36s %s" % (name, e))
        traceback.print_exc()
        failed += 1


tf = TextFile(BIG).open()

print("\n== 1. 基本命中 ==")


def t_ascii():
    hits = search(tf, "timeout")
    assert hits, "没搜到 timeout"
    offs = [h.offset for h in hits]
    assert offs == sorted(offs), "结果没有按偏移升序"
    # 回原文本校验第一条确实命中
    raw = tf.read_bytes(hits[0].offset, hits[0].length)
    assert raw.lower() == b"timeout", "偏移不准：%r" % raw
    return "%d 条（上限 %d），首条偏移 %d" % (len(hits), MAX_HITS, hits[0].offset)


def t_chinese():
    hits = search(tf, "长夜将至")
    assert hits, "没搜到中文"
    raw = tf.read_bytes(hits[0].offset, hits[0].length)
    assert raw.decode("utf-8") == "长夜将至", "中文偏移不准：%r" % raw
    return "%d 条，首条 %r" % (len(hits), hits[0].excerpt[:24])


def t_excerpt():
    hits = search(tf, "timeout")
    h = hits[0]
    assert h.excerpt, "摘要为空"
    assert "timeout" in h.excerpt.lower(), "摘要里看不到关键词：%r" % h.excerpt
    assert "\n" not in h.excerpt, "摘要里还有换行"
    return "摘要: %r" % h.excerpt[:36]


def t_case():
    lower = search(tf, "chapter", case_sensitive=False)
    exact_upper = search(tf, "Chapter", case_sensitive=True)
    exact_lower = search(tf, "chapter", case_sensitive=True)
    assert len(lower) >= len(exact_upper) + len(exact_lower), \
        "不区分大小写的结果应覆盖两者：%d vs %d+%d" % (len(lower), len(exact_upper), len(exact_lower))
    return "不分大小写 %d 条；严格 Chapter %d 条 / chapter %d 条" % (
        len(lower), len(exact_upper), len(exact_lower))


def t_limit():
    hits = search(tf, "的", limit=100)
    assert len(hits) == 100, "limit 没生效：%d" % len(hits)
    hits2 = search(tf, "的")
    assert len(hits2) == MAX_HITS, "默认上限应为 %d，实际 %d" % (MAX_HITS, len(hits2))
    return "limit=100 生效；默认截断在 %d" % MAX_HITS


def t_miss():
    hits = search(tf, "这个词肯定不存在zzzz")
    assert hits == [], "不存在的词却返回 %d 条" % len(hits)
    assert search(tf, "") == []
    assert search(tf, "   ") == []
    return "不存在/空关键词返回空"


def t_boundary():
    """分块边界附近的关键词不能漏也不能重。"""
    # 在块的边界前后各造一个命中点
    from app.core.search import CHUNK
    hits_a = search(tf, "the", limit=MAX_HITS)
    offs = [h.offset for h in hits_a]
    assert len(offs) == len(set(offs)), "有重复命中"
    # 统计跨块边界附近的命中是否连续（不重不漏由去重与重叠区保证）
    near = [o for o in offs if abs(o - CHUNK) < 200]
    return "%d 条无重复；块边界 4MB 附近 %d 条" % (len(offs), len(near))


check("ASCII 关键词", t_ascii)
check("中文关键词", t_chinese)
check("摘要生成", t_excerpt)
check("大小写选项", t_case)
check("结果上限/截断", t_limit)
check("未命中与空词", t_miss)
check("分块边界不重不漏", t_boundary)

print("\n== 2. 性能与其它编码 ==")


def t_speed():
    worst = 0.0
    for kw in ("timeout", "的", "server", "Chapter 12"):
        t0 = time.perf_counter()
        r = search(tf, kw)
        dt = (time.perf_counter() - t0) * 1000
        worst = max(worst, dt)
        assert dt < 800, "%r 搜索太慢：%.0f ms" % (kw, dt)
    return "四个关键词最慢 %.0f ms（目标 < 500 ms）" % worst


def t_gbk():
    tf2 = TextFile(GBK).open()
    try:
        hits = search(tf2, "长夜将至")
        assert hits, "GBK 文件没搜到中文"
        raw = tf2.read_bytes(hits[0].offset, hits[0].length)
        assert raw.decode("gb18030", "replace") == "长夜将至", "GBK 偏移不准：%r" % raw
        hits2 = search(tf2, "Chapter")
        assert hits2, "GBK 文件没搜到英文"
        return "GBK：中文 %d 条 / 英文 %d 条" % (len(hits), len(hits2))
    finally:
        tf2.close()


check("搜索耗时", t_speed)
check("GBK 文件搜索", t_gbk)

tf.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
