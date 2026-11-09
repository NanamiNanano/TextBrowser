# -*- coding: utf-8 -*-
"""目录（章节）识别。

TXT 没有目录结构，只能靠规则推测。为了不在 100 MB 文本上做全文解码，策略是：

1. **先按字节长度过滤**：章节标题不可能超过 200 字节，长行直接跳过——
   长篇小说里 95% 以上是正文段落，这样只需解码几千行而不是 28 万行；
2. 对短行解码后依次套正则，第一个命中即采纳；
3. 命中数太少（< 3）就认为识别失败，返回空列表让界面提示用户，而不是塞一堆垃圾。

层级划分（对应 PRD FR-3.3，最多 3 级）：
  1 级：卷 / 部 / 篇 / 集
  2 级：章 / 回 / 节 / 幕、序章等特殊章、Chapter N
  3 级：【标题】、纯编号行
"""
import re
from dataclasses import dataclass
from typing import List, Optional

MAX_TITLE_BYTES = 200        # 超过这个字节数的行不可能是标题
MAX_TITLE_CHARS = 60         # 解码后再兜一道
MAX_CHAPTERS = 20000         # 防止异常文件把内存打爆
MIN_CHAPTERS = 3             # 少于这个数认为是误识别

# 标题不以这些标点结尾（否则多半是正文句子）
_BAD_TAIL = "，。！？；：、,.;:!?…—）)」』】"

_NUM = r"[0-9０-９〇零一二三四五六七八九十百千两]"

RULES = [
    # (层级, 正则)
    (1, re.compile(r"^第\s*%s{1,8}\s*[卷部篇集]\s*.{0,30}$" % _NUM)),
    (1, re.compile(r"^卷\s*%s{1,8}\s*.{0,30}$" % _NUM)),
    (2, re.compile(r"^第\s*%s{1,8}\s*[章回节幕]\s*.{0,30}$" % _NUM)),
    (2, re.compile(r"^(序章|序言|楔子|引子|前言|后记|尾声|终章|大结局|番外|外传|附录)\s*.{0,30}$")),
    (2, re.compile(r"^(Chapter|CHAPTER|chapter|Part|PART)\s*[0-9IVXLC]{1,8}\s*[:：.\-、]?\s*.{0,40}$")),
    (3, re.compile(r"^【.{1,30}】$")),
    (3, re.compile(r"^[0-9]{1,4}\s*[.、]\s*\S{1,24}$")),
]


@dataclass
class Chapter:
    level: int
    title: str
    offset: int          # 章节标题所在行的起始字节偏移


def _classify(line: str) -> Optional[int]:
    """返回层级，未命中返回 None。"""
    if not line or len(line) > MAX_TITLE_CHARS:
        return None
    if line[-1] in _BAD_TAIL:
        return None
    for level, rx in RULES:
        if rx.match(line):
            return level
    return None


def detect(tf, limit: int = MAX_CHAPTERS) -> List[Chapter]:
    """扫描 TextFile 识别章节。返回空列表表示「没识别出来」。"""
    if tf.size <= 0:
        return []

    enc = tf.encoding or "utf-8"
    found: List[Chapter] = []

    for start, raw in tf.short_lines(MAX_TITLE_BYTES):
        try:
            line = raw.decode(enc, "replace")
        except LookupError:
            line = raw.decode("utf-8", "replace")
        line = line.strip().strip("\ufeff")
        level = _classify(line)
        if level is None:
            continue
        found.append(Chapter(level=level, title=line, offset=start))
        if len(found) >= limit:
            break

    if len(found) < MIN_CHAPTERS:
        return []
    return found


def summary(chapters: List[Chapter]) -> str:
    if not chapters:
        return "未识别到章节"
    lv = {}
    for c in chapters:
        lv[c.level] = lv.get(c.level, 0) + 1
    parts = ["共 %d 个章节" % len(chapters)]
    for k in sorted(lv):
        parts.append("%d级 %d" % (k, lv[k]))
    return "，".join(parts)
