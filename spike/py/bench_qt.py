# -*- coding: utf-8 -*-
"""Qt 文本引擎可行性基准（无头）。

验证目标：Python + PySide6 能否撑起「100 MB 文本秒开 + 低延迟翻页」。
做法：mmap 不整读；行索引只记换行字节偏移；每页只把 ~3k 字符切片交给
QTextDocument 排版，用 hitTest 求页面底部的字符切点，从而得到页边界。

用法: python bench_qt.py <deps_dir> <corpus_file>
"""
import os
import sys
import mmap
import time
import ctypes
import ctypes.wintypes as wt

DEPS = sys.argv[1] if len(sys.argv) > 1 else ""
CORPUS = sys.argv[2] if len(sys.argv) > 2 else "corpus/big_100mb.txt"
if DEPS:
    sys.path.insert(0, DEPS)

os.environ.setdefault("QT_QPA_PLATFORM", os.environ.get("BENCH_QPA", "")) if os.environ.get("BENCH_QPA") else None

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import (QTextDocument, QFont, QTextBlockFormat,  # noqa: E402
                           QTextCursor, QFontMetricsF)
from PySide6.QtCore import QSizeF, QPointF, Qt  # noqa: E402

app = QApplication.instance() or QApplication([])

# 字体真实度自检：中文字宽应≈字号，ASCII 应≈半宽。否则排版数字不可信。
_fm = QFontMetricsF(QFont("Microsoft YaHei"))
print("font check: 中=%.1fpx  A=%.1fpx  (YaHei 20px 期望 中文20 / ASCII10)"
      % (QFontMetricsF(_f := QFont("Microsoft YaHei")).horizontalAdvance("中"),
         _fm.horizontalAdvance("A")))
_w = QFont("Microsoft YaHei")
_w.setPixelSize(20)
_fm20 = QFontMetricsF(_w)
print("font check @20px: 中=%.1f  A=%.1f" % (_fm20.horizontalAdvance("中"), _fm20.horizontalAdvance("A")))

PROP_HEIGHT = int(QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)  # 1


# ---------------------------------------------------------------- memory
class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
    ]


def rss_mb():
    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wt.HANDLE
    k32.GetCurrentProcess.argtypes = []
    psapi.GetProcessMemoryInfo.restype = wt.BOOL
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
    c = PROCESS_MEMORY_COUNTERS()
    c.cb = ctypes.sizeof(c)
    h = k32.GetCurrentProcess()
    psapi.GetProcessMemoryInfo(wt.HANDLE(h), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 1048576


def hr(title):
    print("\n=== %s ===" % title)


results = {}


# ---------------------------------------------------------------- engine
def build_line_index(buf, limit=None):
    """返回换行位置数组（字节偏移）。bytes.find 走 C 层 memchr。"""
    offs = []
    pos = 0
    find = buf.find
    n = len(buf) if limit is None else min(limit, len(buf))
    while pos < n:
        i = find(b"\n", pos)
        if i < 0:
            break
        offs.append(i)
        pos = i + 1
    offs.append(len(buf))
    return offs


def make_doc(width, height, font_family, font_px, line_height):
    doc = QTextDocument()
    doc.setDocumentMargin(0)
    f = QFont(font_family)
    f.setPixelSize(font_px)
    doc.setDefaultFont(f)
    doc.setPageSize(QSizeF(width, height))
    doc._lh = line_height
    return doc


def layout_page(doc, text, width, height):
    """把一段文本塞进 doc，返回一页能容纳的字符数。

    行高用 QTextBlockFormat 施加到全文（Qt 的 QTextOption 在 PySide6 里
    没有暴露 setLineHeight）。
    """
    doc.setPlainText(text)
    lh = getattr(doc, "_lh", None)
    if lh:
        fmt = QTextBlockFormat()
        fmt.setLineHeight(lh * 100.0, PROP_HEIGHT)
        cur = QTextCursor(doc)
        cur.select(QTextCursor.SelectionType.Document)
        cur.mergeBlockFormat(fmt)
    doc.documentLayout().documentSize()  # 强制排版
    pos = doc.documentLayout().hitTest(QPointF(width / 2, height - 1),
                                       Qt.HitTestAccuracy.FuzzyHit)
    if pos <= 0:          # 兜底：hitTest 异常时退化为按行数估算
        pos = min(len(text), 1200)
    return pos


# ---------------------------------------------------------------- main
def main():
    path = CORPUS
    size_mb = os.path.getsize(path) / 1048576
    print("corpus: %s  %.1f MB" % (path, size_mb))
    print("rss at start: %.0f MB" % rss_mb())

    # ---- 1) 打开 + 解码 + 首页 ----
    hr("1. 冷启动：mmap + 读首屏")
    t0 = time.perf_counter()
    f = open(path, "rb")
    buf = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    t_map = (time.perf_counter() - t0) * 1000

    t0 = time.perf_counter()
    head = buf[:4096].decode("utf-8", "replace")
    t_probe = (time.perf_counter() - t0) * 1000

    doc = make_doc(780, 900, "Microsoft YaHei", 20, 1.8)
    t0 = time.perf_counter()
    chunk = buf[:3000 * 3].decode("utf-8", "replace")
    chunk = chunk[:3000]
    first_cut = layout_page(doc, chunk, 780, 900)
    t_first = (time.perf_counter() - t0) * 1000
    print("mmap:            %7.2f ms" % t_map)
    print("首 4KB 解码/探测: %7.2f ms" % t_probe)
    print("首屏排版:        %7.2f ms  (一页容纳 %d 字)" % (t_first, first_cut))
    results["open_to_first_page_ms"] = round(t_map + t_probe + t_first, 2)
    print("合计首屏可见:    %7.2f ms" % results["open_to_first_page_ms"])

    # ---- 2) 行索引 ----
    hr("2. 全文行索引（换行字节偏移）")
    t0 = time.perf_counter()
    lines = build_line_index(buf)
    t_idx = (time.perf_counter() - t0) * 1000
    print("行数:            %d" % len(lines))
    print("索引耗时:        %7.2f ms" % t_idx)
    print("索引内存:        %7.1f MB (Python list of int)" % (len(lines) * 8 / 1048576))
    results["line_index_ms"] = round(t_idx, 2)
    results["lines"] = len(lines)

    # ---- 3) 连续翻页 ----
    hr("3. 连续翻页（每页重新切片 + 排版）")
    for pages in (50, 200):
        doc = make_doc(780, 900, "Microsoft YaHei", 20, 1.8)
        off_bytes = 0
        n = 0
        t0 = time.perf_counter()
        times = []
        dec_bytes = 0
        while n < pages:
            # 按字节取 ~3k 字符的候选窗口（中文 3 字节/字）
            window = 3000 * 3 + 512
            seg = buf[off_bytes:off_bytes + window]
            dec_bytes += len(seg)
            text = seg.decode("utf-8", "ignore")[:3000]
            t1 = time.perf_counter()
            cut_chars = layout_page(doc, text, 780, 900)
            times.append((time.perf_counter() - t1) * 1000)
            # 字符→字节：把切点字符换算成字节偏移
            consumed = text[:cut_chars].encode("utf-8")
            if not consumed:
                break
            off_bytes += len(consumed)
            n += 1
        total = (time.perf_counter() - t0) * 1000
        times.sort()
        print("%3d 页: 总 %7.1f ms | 均值 %5.2f ms | P50 %5.2f ms | P95 %5.2f ms | 最大 %6.2f ms"
              % (pages, total, total / n, times[len(times) // 2],
                 times[int(len(times) * 0.95)], times[-1]))
        if pages == 200:
            results["page_layout_avg_ms"] = round(total / n, 2)
            results["page_layout_p95_ms"] = round(times[int(len(times) * 0.95)], 2)
            results["page_layout_max_ms"] = round(times[-1], 2)

    # ---- 4) 命中缓存的翻页（只取切片，不排版）----
    hr("4. 已建页表后的翻页成本（仅取文本切片）")
    t0 = time.perf_counter()
    N = 2000
    for i in range(N):
        o = (i * 7919) % (len(buf) - 5000)
        _ = buf[o:o + 3000].decode("utf-8", "ignore")
    t_slice = (time.perf_counter() - t0) * 1000
    print("%d 次切片+解码: 总 %7.1f ms | 均值 %5.3f ms" % (N, t_slice, t_slice / N))
    results["slice_avg_ms"] = round(t_slice / N, 3)

    # ---- 5) 全文搜索 ----
    hr("5. 全文搜索（bytes.find 逐次命中）")
    for kw in (b"timeout", "的".encode(), b"Chapter 12"):
        t0 = time.perf_counter()
        cnt = 0
        pos = 0
        while True:
            i = buf.find(kw, pos)
            if i < 0:
                break
            cnt += 1
            pos = i + 1
            if cnt >= 20000:
                break
        dt = (time.perf_counter() - t0) * 1000
        print("关键词 %-12r 命中 %6d 条 | %7.1f ms" % (kw, cnt, dt))
        if kw == b"timeout":
            results["search_ms_100mb"] = round(dt, 1)
            results["search_hits"] = cnt

    # ---- 6) 内存 ----
    hr("6. 内存")
    print("RSS: %.0f MB （含 Qt + 82MB 字体/库）" % rss_mb())
    results["rss_mb"] = round(rss_mb())

    # ---- 7) 窗口尺寸变化后重新分页 ----
    hr("7. 换字号后重新排版一页")
    for px in (14, 20, 28, 40):
        doc = make_doc(780, 900, "Microsoft YaHei", px, 1.8)
        text = buf[:3000 * 4].decode("utf-8", "ignore")[:3800]
        t0 = time.perf_counter()
        cut = layout_page(doc, text, 780, 900)
        dt = (time.perf_counter() - t0) * 1000
        print("%2dpx: %6.2f ms 一页 %4d 字" % (px, dt, cut))

    hr("汇总")
    for k, v in results.items():
        print("%-24s %s" % (k, v))


if __name__ == "__main__":
    main()
