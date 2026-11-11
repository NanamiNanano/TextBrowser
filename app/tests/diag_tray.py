# -*- coding: utf-8 -*-
"""诊断系统托盘图标为什么没出现。

检查：图标对象是否为空、show() 后 Qt 认为可见性如何、系统托盘是否可用。
"""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QSystemTrayIcon

from app.core.settings import Settings
from app.core.library import Library
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss, tray_icon

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = os.path.join(ROOT, "build", "traydiag")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])

print("系统托盘可用:", QSystemTrayIcon.isSystemTrayAvailable())
print("支持气泡消息  :", QSystemTrayIcon.supportsMessages())

icon = tray_icon()
print("tray_icon() 为空:", icon.isNull())
print("可选尺寸:", [ (s.width(), s.height()) for s in icon.availableSizes() ])

s = Settings(os.path.join(TMP, "s.json"))
lib = Library(os.path.join(TMP, "t.db"))
win = MainWindow(s, lib, enable_tray=True)
app.setStyleSheet(build_qss(s))
win.show()
app.processEvents()

t = win.tray
print("托盘对象 isVisible:", t.isVisible())
print("托盘对象 icon 为空:", t.icon().isNull())
print("托盘对象 geometry :", t.geometry())

# 进入事件循环一小会儿，让 Windows 真正把图标加进通知区域
done = {"ok": False}
QTimer.singleShot(1500, lambda: done.__setitem__("ok", True))
while not done["ok"]:
    app.processEvents()

print("事件循环后 isVisible:", t.isVisible())

# 再检查通知区域：枚举 Shell_TrayWnd 下的工具栏按钮数量
import ctypes
import ctypes.wintypes as wt

u32 = ctypes.WinDLL("user32")
u32.FindWindowW.restype = wt.HWND
u32.FindWindowExW.restype = wt.HWND
u32.SendMessageW.restype = ctypes.c_ssize_t


def count_icons(hwnd_parent, label):
    tb = u32.FindWindowExW(hwnd_parent, None, "ToolbarWindow32", None)
    if not tb:
        print("  %s: 找不到 ToolbarWindow32" % label)
        return 0
    TB_BUTTONCOUNT = 0x0418
    n = u32.SendMessageW(tb, TB_BUTTONCOUNT, 0, 0)
    print("  %s: 按钮数 = %d" % (label, n))
    return n


tray = u32.FindWindowW("Shell_TrayWnd", None)
print("Shell_TrayWnd:", tray)
count_icons(tray, "主通知区域")
overflow = u32.FindWindowW("NotifyIconOverflowWindow", None)
print("NotifyIconOverflowWindow:", overflow)
if overflow:
    count_icons(overflow, "溢出区")

win._stop_worker()
win.hide()
lib.close()
