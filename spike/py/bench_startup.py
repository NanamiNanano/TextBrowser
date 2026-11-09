# -*- coding: utf-8 -*-
"""测量 Python + Qt 的进程冷启动成本（不含打包后的 PyInstaller 开销）。"""
import statistics
import subprocess
import sys
import time

vendor = sys.argv[1]

probe = (
    "import sys, time\n"
    "sys.path.insert(0, r'__VENDOR__')\n"
    "t = time.perf_counter()\n"
    "from PySide6.QtWidgets import QApplication\n"
    "from PySide6.QtGui import QTextDocument, QFont\n"
    "app = QApplication([])\n"
    "d = QTextDocument()\n"
    "d.setPlainText('x' * 500)\n"
    "d.documentLayout().documentSize()\n"
    "print('%.0f' % ((time.perf_counter() - t) * 1000))\n"
).replace("__VENDOR__", vendor)

qt_ms = []
total_ms = []
for _ in range(3):
    t0 = time.perf_counter()
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True)
    dt = (time.perf_counter() - t0) * 1000
    total_ms.append(dt)
    if r.returncode == 0 and r.stdout.strip():
        qt_ms.append(float(r.stdout.strip()))
    else:
        print("probe stderr:", (r.stderr or "").strip()[:300])

print("import Qt6 + QApplication + 首个文档: " +
      ", ".join("%.0fms" % t for t in qt_ms) +
      " | 均值 %.0fms" % (statistics.mean(qt_ms) if qt_ms else -1))
print("完整进程冷启动(解释器+导入+退出): " +
      ", ".join("%.0fms" % t for t in total_ms) +
      " | 均值 %.0fms" % statistics.mean(total_ms))
print("说明: PyInstaller 打包后还要加 100~400ms 的解包/加载开销。")
