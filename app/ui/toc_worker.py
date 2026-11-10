# -*- coding: utf-8 -*-
"""目录识别的后台工作线程。

100 MB TXT 的「建索引 + 识别」约 170 ms，放在主线程会把首屏之后的交互卡住。
这里用独立线程 + **独立的 TextFile 实例**（各自的 mmap），因此不需要加锁；
结果通过 Qt 信号回到主线程后再写数据库，避免跨线程动同一个 sqlite 连接。

即使 Python 的 GIL 会让主线程的 Python 代码短暂等待，Qt 的 C++ 事件循环
（绘制、拖动窗口）仍然继续，比同步阻塞在事件处理器里好得多。
"""
from PySide6.QtCore import QThread, Signal

from ..core import toc as toc_rules
from ..core.textfile import TextFile


class ChapterWorker(QThread):
    finished_ok = Signal(int, list)      # book_id, [Chapter]
    failed = Signal(int, str)            # book_id, 错误信息

    def __init__(self, book_id: int, path: str, encoding, parent=None):
        super().__init__(parent)
        self.book_id = int(book_id)
        self.path = path
        self.encoding = encoding

    def run(self):
        tf = None
        try:
            tf = TextFile(self.path, encoding=self.encoding)
            tf.open()
            chapters = toc_rules.detect(tf)
            self.finished_ok.emit(self.book_id, chapters)
        except Exception as e:                      # noqa: BLE001
            self.failed.emit(self.book_id, str(e))
        finally:
            if tf is not None:
                tf.close()
