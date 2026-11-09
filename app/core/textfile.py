# -*- coding: utf-8 -*-
"""大文本文件访问：mmap + 换行索引。

进度基准用「字节偏移」而不是字符偏移：切换字体/字号/窗口尺寸、甚至改编码
都不会让它失效，稳定性优于字符偏移（字符偏移需要先整本解码）。
"""
import codecs
import mmap
import os
from array import array
from typing import List, Optional, Tuple

from .encoding import detect_chunks, decode_with_fallback

SAMPLE_BYTES = 256 * 1024


class TextFile:
    def __init__(self, path: str, encoding: Optional[str] = None):
        self.path = path
        self.size = os.path.getsize(path)
        self.encoding = encoding
        self.confidence = 1.0 if encoding else 0.0
        self._fh = None
        self._mm: Optional[mmap.mmap] = None
        self._line_offsets: Optional[array] = None
        self._char_count = -1
        self._newline = "\n"

    # ------------------------------------------------------------ 生命周期
    def open(self) -> "TextFile":
        if self._mm is not None:
            return self
        self._fh = open(self.path, "rb")
        if self.size == 0:
            self._mm = mmap.mmap(-1, 0)  # 空文件占位
        else:
            self._mm = mmap.mmap(self._fh.fileno(), 0, access=mmap.ACCESS_READ)
        if self.encoding is None:
            self.encoding, self.confidence = detect_chunks(self._samples())
        self._newline = self._detect_newline()
        return self

    def close(self) -> None:
        if self._mm is not None:
            try:
                self._mm.close()
            except (BufferError, ValueError):
                pass
            self._mm = None
        if self._fh is not None:
            self._fh.close()
            self._fh = None

    def __enter__(self):
        return self.open()

    def __exit__(self, *exc):
        self.close()

    # ------------------------------------------------------------ 采样
    def _samples(self) -> List[bytes]:
        if not self.size:
            return []
        chunks = [self._mm[:min(SAMPLE_BYTES, self.size)]]
        if self.size > SAMPLE_BYTES * 4:
            mid = self.size // 2
            chunks.append(self._mm[mid:mid + SAMPLE_BYTES // 2])
        return chunks

    def _sample(self) -> bytes:
        return b"".join(self._samples())

    def _detect_newline(self) -> str:
        head = self._mm[:65536]
        crlf = head.count(b"\r\n")
        lf = head.count(b"\n") - crlf
        cr = head.count(b"\r") - crlf
        if crlf >= lf and crlf >= cr:
            return "\r\n"
        if cr >= lf and cr > 0:
            return "\r"
        return "\n"

    @property
    def newline(self) -> str:
        return self._newline

    # ------------------------------------------------------------ 索引
    def build_index(self) -> int:
        """记录每个换行之后的位置，返回行数。100MB 约 90ms（实测）。"""
        if self._line_offsets is not None:
            return len(self._line_offsets)
        offs = array("Q")
        offs.append(0)
        if self.size:
            find = self._mm.find
            pos = 0
            while True:
                i = find(b"\n", pos)
                if i < 0:
                    break
                offs.append(i + 1)
                pos = i + 1
        self._line_offsets = offs
        return len(offs)

    @property
    def line_count(self) -> int:
        return len(self._line_offsets) if self._line_offsets is not None else 0

    def line_start(self, index: int) -> int:
        if self._line_offsets is None:
            self.build_index()
        return self._line_offsets[index]

    def line_of_offset(self, offset: int) -> int:
        """二分找 offset 所在行。"""
        if self._line_offsets is None:
            self.build_index()
        lo, hi = 0, len(self._line_offsets) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._line_offsets[mid] <= offset:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def short_lines(self, max_bytes: int):
        """产出 (字节偏移, 该行原始字节)，只返回长度 <= max_bytes 的行。

        目录识别只关心短行。原先在 toc.py 里逐行调 line_start()/read_bytes()
        遍历 28 万行要 2.3 秒；把长度判断和 mmap 切片放到这里，可以压到 0.3 秒
        以内，同时让 mmap 保持私有，不让上层碰内部结构。
        """
        if self._line_offsets is None:
            self.build_index()
        offs = self._line_offsets
        n = len(offs)
        mm = self._mm
        size = self.size
        for i in range(n):
            start = offs[i]
            end = offs[i + 1] if i + 1 < n else size
            if end - start > max_bytes or end - start <= 1:
                continue
            yield start, mm[start:end]

    # ------------------------------------------------------------ 读取
    def align_offset(self, offset: int) -> int:
        """把任意字节偏移挪到字符边界上。

        用户拖动进度条、或历史版本存下的偏移，可能落在多字节字符中间；直接从
        那里解码会产生乱码（UTF-8 是一个 U+FFFD 方块，GBK/Big5 是成片的生僻字）。

        * UTF-8：后续字节高两位恒为 10，向后跳过即可，O(1)。
        * GBK/Big5 等双字节编码：无法从单个字节判断，改为「回到本行行首，
          用 ignore 解码掉末尾残缺字符，再按编码后的字节数推出边界」。
        """
        if self.size == 0:
            return 0
        off = max(0, min(offset, self.size))
        if off == 0 or off >= self.size:
            return off

        enc = self.encoding or "utf-8"
        if enc in ("utf-8", "utf-8-sig"):
            while off < self.size and (self._mm[off] & 0xC0) == 0x80:
                off += 1
            return off

        # 双字节编码：以行首为锚点重算（行内长度有限，代价可忽略）
        window_start = max(0, off - 8192)
        nl = self._mm.rfind(b"\n", window_start, off)
        anchor = nl + 1 if nl >= 0 else window_start
        try:
            prefix = self._mm[anchor:off].decode(enc, "ignore")
            return anchor + len(prefix.encode(enc, "ignore"))
        except (LookupError, UnicodeError):
            return off

    def read_bytes(self, start: int, length: int) -> bytes:
        start = max(0, min(start, self.size))
        end = min(self.size, start + length)
        return self._mm[start:end] if self.size else b""

    @property
    def buffer(self):
        """底层 mmap，只读。搜索这类需要整片扫描的场景用它，避免逐块复制。"""
        if self._mm is None:
            raise RuntimeError("文件未打开，先调用 open()")
        return self._mm

    def decode(self, start: int, length: int, errors: str = "replace") -> str:
        return decode_with_fallback(self.read_bytes(start, length), self.encoding) \
            if errors == "replace" else self.read_bytes(start, length).decode(self.encoding)

    def read_window(self, start: int, length: int) -> str:
        """按字符边界对齐地读一段，避免把多字节字符劈成两半。"""
        raw = self.read_bytes(start, length)
        enc = self.encoding or "utf-8"
        dec = codecs.getincrementaldecoder(enc)(errors="replace")
        return dec.decode(raw, final=False)

    def char_count(self) -> int:
        """整本字符数（首次调用需全量解码，100MB 约 1~2s，慎用）。"""
        if self._char_count >= 0:
            return self._char_count
        total = 0
        step = 4 * 1024 * 1024
        dec = codecs.getincrementaldecoder(self.encoding or "utf-8")(errors="replace")
        pos = 0
        while pos < self.size:
            n = min(step, self.size - pos)
            total += len(dec.decode(self._mm[pos:pos + n], final=False))
            pos += n
        total += len(dec.decode(b"", final=True))
        self._char_count = total
        return total

    # ------------------------------------------------------------ 统计
    def stats(self) -> dict:
        return {
            "path": self.path,
            "size": self.size,
            "encoding": self.encoding,
            "confidence": round(self.confidence, 2),
            "newline": repr(self.newline),
            "lines": self.line_count,
        }


def probe_encoding(path: str) -> Tuple[str, float]:
    """不打开整个文件，只采样判断编码。"""
    chunks = []
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        chunks.append(f.read(SAMPLE_BYTES))
        if size > SAMPLE_BYTES * 4:
            f.seek(size // 2)
            chunks.append(f.read(SAMPLE_BYTES // 2))
    return detect_chunks(chunks)
