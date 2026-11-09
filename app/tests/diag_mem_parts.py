# -*- coding: utf-8 -*-
"""逐组件称重：找出 show() 时吃 300MB 的元凶。"""
import ctypes
import ctypes.wintypes as wt
import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class PMC(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD),
                ("a", ctypes.c_size_t), ("b", ctypes.c_size_t),
                ("c", ctypes.c_size_t), ("d", ctypes.c_size_t),
                ("e", ctypes.c_size_t), ("f", ctypes.c_size_t),
                ("g", ctypes.c_size_t), ("h", ctypes.c_size_t)]


def mem():
    psapi = ctypes.WinDLL("psapi")
    k32 = ctypes.WinDLL("kernel32")
    k32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.c_void_p, wt.DWORD]
    c = PMC()
    c.cb = ctypes.sizeof(c)
    psapi.GetProcessMemoryInfo(wt.HANDLE(k32.GetCurrentProcess()), ctypes.byref(c), c.cb)
    return c.b / 1048576


from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from app.core.library import Library  # noqa: E402
from app.core.settings import Settings  # noqa: E402
from app.ui.bookshelf import BookshelfView  # noqa: E402
from app.ui.reader import ReaderView  # noqa: E402
from app.ui.titlebar import TitleBar  # noqa: E402
from app.ui.tray import Tray  # noqa: E402

app = QApplication([])
TMP = os.path.join(ROOT, "build", "shot_tmp")
os.makedirs(TMP, exist_ok=True)
settings = Settings(os.path.join(TMP, "parts_settings.json"))
library = Library(os.path.join(TMP, "parts.db"))

base = mem()
print("基线 %.1f MB\n" % base)

keep = []


def weigh(name, factory):
    global base
    before = mem()
    w = factory()
    keep.append(w)
    w.resize(1120, 780)
    w.show()
    app.processEvents()
    after = mem()
    w.hide()
    app.processEvents()
    print("  %-24s %+8.1f MB   (累计 %.1f)" % (name, after - before, after))
    base = after


weigh("空 QWidget", lambda: QWidget())
weigh("TitleBar", lambda: TitleBar())
weigh("BookshelfView", lambda: BookshelfView(library))
weigh("ReaderView", lambda: ReaderView(settings, library))
weigh("Tray(构造)", lambda: Tray(lambda: []))

# 组件全都没问题的话，再单独测 QSS
from app.ui.theme import build_qss  # noqa: E402

before = mem()
app.setStyleSheet(build_qss(settings))
app.processEvents()
print("  %-24s %+8.1f MB" % ("应用 QSS 后", mem() - before))

w = QWidget()
w.resize(1120, 780)
before = mem()
w.show()
app.processEvents()
print("  %-24s %+8.1f MB" % ("带 QSS 的空窗口 show", mem() - before))
keep.append(w)
