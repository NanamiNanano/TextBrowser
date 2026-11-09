# -*- coding: utf-8 -*-
"""文本编码检测。

策略（不依赖第三方库，保证离线可用）：
  1. BOM 优先；
  2. 大量 NUL 字节 → UTF-16/32；
  3. UTF-8 严解码通过即判定（它是自校验编码，误判率极低）；
  4. 否则按「可打印率 + 汉字占比」在 GB18030 / Big5 之间挑。

注意：第 3 步必须优先于 UTF-16 的盲目尝试。把任意 UTF-8 中文字节流按
utf-16-le 解码，几乎总能落在汉字区，纯粹按「汉字占比」打分会一路误判。
"""
from typing import List, Tuple

import codecs

BOMS = [
    (b"\xef\xbb\xbf", "utf-8"),
    (b"\xff\xfe\x00\x00", "utf-32-le"),
    (b"\x00\x00\xfe\xff", "utf-32-be"),
    (b"\xff\xfe", "utf-16-le"),
    (b"\xfe\xff", "utf-16-be"),
]

LEGACY_CANDIDATES = ["gb18030", "big5"]

# 高频汉字，用于区分 GBK / Big5 这类互相能"解通但解错"的编码
COMMON_HANZI = set(
    "的一是了我不人在他有这个上们来到时大地为子中你说生国年着就那和要她出也得里"
    "后自以会家可下而过天去能对小多然于心学么之都好看起发当没成只如事把还用第样"
    "道想作种开美总从无情己面最女但现前些所同日手又行意动方期它头经长儿回位分爱"
    "老因很给名法间斯知世什两次使身者被高已亲其进此话常与活正感见明问力理尔点文"
)


def _printable_ratio(text: str) -> float:
    if not text:
        return 0.0
    good = 0
    for ch in text:
        o = ord(ch)
        if o >= 32 or ch in "\n\r\t":
            if not (0xFFFD == o):          # 替换符算坏字符
                good += 1
    return good / len(text)


def _cjk_ratio(text: str) -> float:
    if not text:
        return 0.0
    n = 0
    for ch in text:
        o = ord(ch)
        if 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF:
            n += 1
    return n / len(text)


def _common_ratio(text: str) -> float:
    """高频汉字占全部汉字的比例，用来区分 GBK/Big5。"""
    hanzi = [ch for ch in text if 0x4E00 <= ord(ch) <= 0x9FFF]
    if not hanzi:
        return 0.0
    return sum(1 for ch in hanzi if ch in COMMON_HANZI) / len(hanzi)


def detect(sample: bytes) -> Tuple[str, float]:
    """返回 (编码, 置信度 0~1)。"""
    if not sample:
        return "utf-8", 0.0

    # 1) BOM
    for bom, enc in BOMS:
        if sample.startswith(bom):
            return enc, 1.0

    # 2) UTF-16/32（无 BOM）
    nul = sample.count(b"\x00")
    if nul > len(sample) * 0.25:
        for enc in ("utf-16-le", "utf-16-be"):
            try:
                text = sample.decode(enc)
            except UnicodeDecodeError:
                continue
            if _printable_ratio(text) > 0.95 and _cjk_ratio(text) > 0.10:
                return enc, 0.85

    # 3) UTF-8 自校验（用增量解码容忍采样末尾被切断的多字节字符）
    try:
        dec = codecs.getincrementaldecoder("utf-8")(errors="strict")
        text = dec.decode(sample, final=False)
        if text and _printable_ratio(text) > 0.98:
            return "utf-8", 0.98
    except UnicodeDecodeError:
        pass

    # 4) 东亚传统编码
    best_enc, best_score = "gb18030", -99.0
    for enc in LEGACY_CANDIDATES:
        try:
            text = sample.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
        pr = _printable_ratio(text)
        cj = _cjk_ratio(text)
        cm = _common_ratio(text)
        if pr < 0.90:
            continue
        score = pr * 1.0 + min(cj, 0.9) * 1.5 + cm * 2.0
        if enc == "gb18030":
            score += 0.05           # 中文环境先验
        if score > best_score:
            best_enc, best_score = enc, score

    if best_score > 0:
        return best_enc, max(0.4, min(0.95, best_score / 4.0))
    return "utf-8", 0.3


def decode_with_fallback(raw: bytes, encoding: str) -> str:
    try:
        return raw.decode(encoding)
    except (UnicodeDecodeError, LookupError):
        try:
            return raw.decode(encoding, errors="replace")
        except LookupError:
            return raw.decode("utf-8", errors="replace")


def detect_chunks(chunks: List[bytes]) -> Tuple[str, float]:
    """对多个不相邻的采样块分别检测后投票，避免单块边界处的偶发误判。"""
    chunks = [c for c in chunks if c]
    if not chunks:
        return "utf-8", 0.0
    if len(chunks) == 1:
        return detect(chunks[0])

    votes = {}
    for c in chunks:
        enc, conf = detect(c)
        cur = votes.get(enc, [0.0, 0])
        votes[enc] = [cur[0] + conf, cur[1] + 1]

    # 优先级：块数多的优先，其次总分
    best_enc, (total, count) = max(
        votes.items(), key=lambda kv: (kv[1][1], kv[1][0]))
    return best_enc, min(1.0, total / max(1, len(chunks)))
