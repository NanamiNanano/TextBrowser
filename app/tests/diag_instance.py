# -*- coding: utf-8 -*-
"""验证单实例方案可行性：命名互斥体 + EnumWindows 唤起窗口。

QLocalServer 在所有沙箱模式下都被禁（底层是命名管道），所以换成纯 Win32：
  * CreateMutexW 判断是否已有实例（内核对象，不走管道）；
  * EnumWindows 按标题前缀找到已有窗口，ShowWindow + SetForegroundWindow 唤起。
"""
import ctypes
import ctypes.wintypes as wt

k32 = ctypes.WinDLL("kernel32", use_last_error=True)
u32 = ctypes.WinDLL("user32", use_last_error=True)

ERROR_ALREADY_EXISTS = 183
MUTEX_NAME = "Global\\TextBrowser-Instance-Probe"      # 换成 Local\\ 也行，Global 需要权限
MUTEX_NAME_LOCAL = "TextBrowser-Instance-Probe-Local"

print("=== 1) 命名互斥体 Global\\ ===")
k32.CreateMutexW.restype = wt.HANDLE
k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
h1 = k32.CreateMutexW(None, False, MUTEX_NAME)
err1 = ctypes.get_last_error()
print("   句柄=%s err=%d  已存在=%s" % (bool(h1), err1, err1 == ERROR_ALREADY_EXISTS))

print("=== 2) 命名互斥体 Local\\（无 Global 权限时用）===")
h2 = k32.CreateMutexW(None, False, MUTEX_NAME_LOCAL)
err2 = ctypes.get_last_error()
print("   句柄=%s err=%d  已存在=%s" % (bool(h2), err2, err2 == ERROR_ALREADY_EXISTS))
if h2:
    h2b = k32.CreateMutexW(None, False, MUTEX_NAME_LOCAL)
    err2b = ctypes.get_last_error()
    print("   同名再创建：已存在=%s  (第二次应为 True)" % (err2b == ERROR_ALREADY_EXISTS))

print("=== 3) EnumWindows 枚举可见窗口 ===")
k32.CreateMutexW(MUTEX_NAME_LOCAL and None, False, MUTEX_NAME_LOCAL)
u32.EnumWindows.restype = wt.BOOL
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetWindowTextLengthW.argtypes = [wt.HWND]

ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
found = []


def _cb(hwnd, _lp):
    if not u32.IsWindowVisible(hwnd):
        return True
    n = u32.GetWindowTextLengthW(hwnd)
    if n <= 0:
        return True
    buf = ctypes.create_unicode_buffer(n + 1)
    u32.GetWindowTextW(hwnd, buf, n + 1)
    title = buf.value
    if title.strip():
        found.append((hwnd, title))
    return True


u32.EnumWindows(ENUMPROC(_cb), 0)
print("   共枚举到 %d 个有标题的可见窗口，前 8 个：" % len(found))
for hwnd, t in found[:8]:
    print("     %s  %s" % (hwnd, t[:50]))

print("=== 4) 结论 ===")
print("   互斥体可用:", bool(h1 or h2))
print("   EnumWindows 可用:", len(found) > 0)
