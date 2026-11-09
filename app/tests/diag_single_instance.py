# -*- coding: utf-8 -*-
"""验证双击入口的单实例行为：用 Python 自己拉起两个实例，看第二个是否退出。

用 subprocess 而不是 PowerShell 的 Start-Process，避免启动方式本身影响进程
所属的命名对象空间。
"""
import os
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LAUNCHER = os.path.join(ROOT, "launcher.py")
LOG = os.path.join(ROOT, "build")
os.makedirs(LOG, exist_ok=True)


def spawn(tag):
    out = open(os.path.join(LOG, "inst_%s.out" % tag), "wb")
    err = open(os.path.join(LOG, "inst_%s.err" % tag), "wb")
    return subprocess.Popen([sys.executable, LAUNCHER], cwd=ROOT,
                            stdout=out, stderr=err), out, err


print("启动实例 1 ...")
p1, o1, e1 = spawn("1")
time.sleep(5)
print("  实例 1 存活:", p1.poll() is None)

print("启动实例 2 ...")
p2, o2, e2 = spawn("2")
exited = None
for _ in range(16):                 # 最多等 8 秒
    if p2.poll() is not None:
        exited = p2.returncode
        break
    time.sleep(0.5)

if exited is None:
    print("  ✗ 实例 2 仍在运行 -> 单实例失效（起了两个窗口）")
else:
    print("  ✓ 实例 2 已退出，退出码 =", exited)

print("  实例 1 是否还活着:", p1.poll() is None)

# 收集错误输出
for tag, f in (("1", e1), ("2", e2)):
    f.flush()
    f.close()
    path = os.path.join(LOG, "inst_%s.err" % tag)
    if os.path.getsize(path):
        print("  --- 实例 %s stderr ---" % tag)
        with open(path, encoding="utf-8", errors="replace") as fh:
            print("   " + fh.read().strip()[:600].replace("\n", "\n   "))

for p in (p1, p2):
    if p.poll() is None:
        p.kill()

raise SystemExit(0 if exited is not None else 1)
