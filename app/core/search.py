# -*- coding: utf-8 -*-
"""全文搜索。

直接在 mmap 的字节流上匹配，不整本解码：
  * `bytes.find` 走 C 层 memchr/memmem，100 MB 文本几十毫秒；
  * 区分大小写时直接比字节；不区分时按 4 MB 分块 `lower()` 再比，
    因为 `bytes.lower()` 只改写 0x41-0x5A，不改变长度也不会破坏多字节字符，
    所以块内命中位置可以直接换算成全局偏移；
  * 分块会切断关键词，所以要带 `len(needle)-1` 的重叠区，并把重叠区里的
    重复命中丢掉。
"""
import codecs
from dataclasses import dataclass
from typing import List

CHUNK = 4 << 20           # 4 MB
MAX_HITS = 5000           # 结果上限，超出就截断（PRD FR-11.7）
CONTEXT_BYTES = 60        # 摘要取命中前后各多少字节


@dataclass
class Hit:
    offset: int           # 命中处的字节偏移
    length: int           # 命中长度（字节）
    excerpt: str          # 上下文摘要（已把换行压成空格）

    @property
    def end(self) -> int:
        return self.offset + self.length


def _excerpt(tf, off: int, length: int) -> str:
    start = tf.align_offset(max(0, off - CONTEXT_BYTES))
    end = min(tf.size, off + length + CONTEXT_BYTES)
    raw = tf.read_bytes(start, end - start)
    try:
        text = raw.decode(tf.encoding or "utf-8", "replace")
    except LookupError:
        text = raw.decode("utf-8", "replace")
    # 用原文的命中片段定位，保证摘要里能看到关键词本身
    text = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return " ".join(text.split())


def search(tf, keyword: str, case_sensitive: bool = False,
           limit: int = MAX_HITS) -> List[Hit]:
    """返回命中列表（按文件顺序）。空关键词返回空列表。"""
    keyword = keyword or ""
    if not keyword.strip() or tf.size <= 0:
        return []

    enc = tf.encoding or "utf-8"
    try:
        needle = keyword.encode(enc, "ignore")
    except LookupError:
        needle = keyword.encode("utf-8", "ignore")
    if not needle:
        return []

    buf = tf.buffer
    hits: List[Hit] = []
    ignore_case = (not case_sensitive) and keyword.lower() != keyword.upper()

    if not ignore_case:
        pos = 0
        while len(hits) < limit:
            i = buf.find(needle, pos)
            if i < 0:
                break
            hits.append(Hit(i, len(needle), _excerpt(tf, i, len(needle))))
            pos = i + 1
        return hits

    # 不区分大小写：分块小写化后匹配
    low_needle = needle.lower()
    overlap = len(low_needle) - 1
    start = 0
    size = tf.size
    while start < size and len(hits) < limit:
        end = min(size, start + CHUNK + overlap)
        chunk = buf[start:end].lower()
        base = start
        pos = 0
        while len(hits) < limit:
            i = chunk.find(low_needle, pos)
            if i < 0:
                break
            # 重叠区里重复出现的命中要丢掉（上一块已经收过）
            if i < overlap and start > 0:
                pos = i + 1
                continue
            g = base + i
            hits.append(Hit(g, len(needle), _excerpt(tf, g, len(needle))))
            pos = i + 1
        start = end - overlap if end < size else size

    return hits


def count_only(tf, keyword: str, case_sensitive: bool = False) -> int:
    """只数命中数，不生成摘要（用于界面上的「约 N 条」预览）。"""
    return len(search(tf, keyword, case_sensitive, limit=MAX_HITS))
