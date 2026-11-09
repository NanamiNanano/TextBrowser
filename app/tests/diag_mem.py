# -*- coding: utf-8 -*-
"""分阶段测量内存占用，定位增长来源。"""
import ctypes
import ctypes.wintypes as wt
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t)]


def mem():
    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(wt.HANDLE(k32.GetCurrentProcess()), ctypes.byref(c), c.cb)
    return c.WorkingSetSize / 1048576, c.PagefileUsage / 1048576


def mark(label):
    ws, priv = mem()
    print("  %-34s 工作集 %6.1f MB   私有 %6.1f MB" % (label, ws, priv))


print("分阶段内存:")
mark("Python 启动")

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

mark("import PySide6")

app = QApplication([])
mark("QApplication")

from app.core.library import Library  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.ui.main_window import MainWindow  # noqa: E402
from app.ui.theme import build_qss  # noqa: E402

mark("import 本项目模块")

TMP = os.path.join(ROOT, "build", "shot_tmp")
os.makedirs(TMP, exist_ok=True)
settings = Settings(os.path.join(TMP, "mem_settings.json"))
library = Library(os.path.join(TMP, "mem.db"))
mark("Settings + Library（SQLite）")

win = MainWindow(settings, library, enable_tray=False)
mark("MainWindow 构造完成")

app.setStyleSheet(build_qss(settings))
mark("应用 QSS")

win.show()
app.processEvents()
mark("show() + 首帧")

# 空转 4 秒，看是否持续增长
import time
t0 = time.time()
while time.time() - t0 < 4:
    app.processEvents()
    time.sleep(0.02)
mark("空转 4 秒后")

BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
bid = library.add_file(BIG)
win.open_book(bid)
app.processEvents()
mark("打开 100MB 文档")

win.reader.next_page()
app.processEvents()
mark("翻 1 页")

t0 = time.time()
while time.time() - t0 < 3:
    app.processEvents()
    time.sleep(0.02)
mark("再空转 3 秒")

win.hide()
library.close()
