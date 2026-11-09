# -*- coding: utf-8 -*-
"""跨进程验证单实例互斥体：一个进程持有 N 秒，另一个进程看是否被拦住。

用法: python -m app.tests.diag_instance2 <hold秒数|0>
"""
import sys
import time

from app.core import instance

hold = float(sys.argv[1]) if len(sys.argv) > 1 else 0
name = "TextBrowser-DiagMutex-v1"

ok = instance.acquire(name)
print("acquire -> %s (是否本进程为唯一实例)" % ok, flush=True)

if hold > 0:
    print("持有 %.1f 秒..." % hold, flush=True)
    time.sleep(hold)
print("结束 pid=%d" % __import__("os").getpid(), flush=True)
