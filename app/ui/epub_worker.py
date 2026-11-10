# -*- coding: utf-8 -*-
"""EPUB 转换的后台线程。

一本 10 MB / 1587 个文件的 EPUB 实测转换约 1 秒，但这个耗时随书增长，
而且转换期间不能让窗口卡死，所以放线程里跑，并通过信号回报进度。
"""
from PySide6.QtCore import QThread, Signal

from ..core import epub


class EpubWorker(QThread):
    progressed = Signal(int, int)        # 已完成, 总数
    finished_ok = Signal(object)         # EpubResult
    failed = Signal(str)

    def __init__(self, epub_path: str, cache_path: str, parent=None):
        super().__init__(parent)
        self.epub_path = epub_path
        self.cache_path = cache_path
        self._cancel = False

    def request_cancel(self) -> None:
        self._cancel = True

    def _on_progress(self, done: int, total: int) -> bool:
        if self._cancel:
            return False
        self.progressed.emit(done, total)
        return True

    def run(self):
        try:
            result = epub.convert(self.epub_path, self.cache_path,
                                  progress=self._on_progress)
            if self._cancel:
                return
            self.finished_ok.emit(result)
        except Exception as e:                       # noqa: BLE001
            self.failed.emit(str(e))
