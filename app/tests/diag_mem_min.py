# -*- coding: utf-8 -*-
"""最小对照：裸 QWidget 显示前后的内存，判断 +300MB 是不是 Qt 平台层固有开销。"""
import ctypes
import ctypes.wintypes as wt

from PySide6.QtWidgets import QApplication, QLabel, QWidget


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
    return c.b / 1048576, c.g / 1048576


def mark(s):
    ws, pv = mem()
    print("  %-30s 工作集 %6.1f MB  私有 %6.1f MB" % (s, ws, pv))


mark("import 完成")
app = QApplication([])
mark("QApplication")
w = QWidget()
mark("QWidget 构造")
w.resize(1120, 780)
w.show()
mark("show()")
app.processEvents()
mark("首帧 processEvents")
print("  platform =", app.platformName())

lbl = QLabel("文本浏览器 测试 ABC 123", w)
lbl.move(40, 40)
lbl.show()
app.processEvents()
mark("画一段中文后")

import time
t0 = time.time()
while time.time() - t0 < 3:
    app.processEvents()
    time.sleep(0.02)
mark("空转 3 秒")
w.hide()
