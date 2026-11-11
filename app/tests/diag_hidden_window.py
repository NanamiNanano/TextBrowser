# -*- coding: utf-8 -*-
"""辅助脚本：造一个「标题是 文本浏览器、但已隐藏」的窗口并保持存活。

用来验证 instance.activate() 能否找到**已隐藏**的窗口——这正是
「按 ESC 收进托盘后再双击 exe」时会发生的情况。

用法: python -m app.tests.diag_hidden_window <保持秒数>
"""
import sys
import time

from PySide6.QtWidgets import QApplication, QWidget

app = QApplication([])
w = QWidget()
w.setWindowTitle("文本浏览器")
w.resize(400, 300)
w.show()
app.processEvents()
time.sleep(0.5)
w.hide()                      # 收进托盘后的状态：窗口存在但不可见
app.processEvents()
print("已隐藏，windowHandle 有效:", w.windowHandle() is not None, flush=True)
time.sleep(float(sys.argv[1]) if len(sys.argv) > 1 else 10)
