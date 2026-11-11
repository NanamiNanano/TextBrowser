# -*- coding: utf-8 -*-
"""实验：PySide6 槽函数里抛异常，进程会怎样？sys.excepthook 能不能兜住？

这决定了「按 ESC 程序直接消失」是不是异常导致的，以及我们的 excepthook
到底有没有用。
"""
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

hits = []


def hook(exc_type, exc, tb):
    hits.append("%s: %s" % (exc_type.__name__, exc))
    print("[excepthook] 捕获:", hits[-1], flush=True)


sys.excepthook = hook

app = QApplication([])


def boom():
    raise RuntimeError("故意在槽函数里抛异常")


print("[1] 准备在 100ms 后抛异常", flush=True)
QTimer.singleShot(100, boom)
QTimer.singleShot(500, app.quit)

print("[2] 进入事件循环", flush=True)
code = app.exec()
print("[3] 事件循环结束，返回码 =", code, flush=True)
print("[4] excepthook 命中次数 =", len(hits), flush=True)
print("[5] 进程还活着" if len(hits) else "[5] 异常没经过 excepthook", flush=True)
