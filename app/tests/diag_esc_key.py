# -*- coding: utf-8 -*-
"""用 keybd_event 发一个真实 ESC（SendInput 在受限环境会被拦，返回 0）。

用法: python -m app.tests.diag_esc_key [窗口标题前缀]
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

u32 = ctypes.WinDLL("user32", use_last_error=True)
u32.EnumWindows.restype = wt.BOOL
u32.GetWindowTextLengthW.argtypes = [wt.HWND]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.SetForegroundWindow.argtypes = [wt.HWND]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.keybd_event.argtypes = [wt.BYTE, wt.BYTE, wt.DWORD, ctypes.c_size_t]

ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)
PREFIX = sys.argv[1] if len(sys.argv) > 1 else "文本浏览器"


def find():
    out = []

    def cb(h, _l):
        n = u32.GetWindowTextLengthW(h)
        if n > 0:
            b = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(h, b, n + 1)
            if b.value.startswith(PREFIX):
                pid = wt.DWORD(0)
                u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
                out.append((h, b.value, pid.value, bool(u32.IsWindowVisible(h))))
        return True

    u32.EnumWindows(ENUMPROC(cb), 0)
    return out


wins = find()
print("窗口:", [(hex(h), t, p, v) for h, t, p, v in wins])
if not wins:
    sys.exit(2)

hwnd, title, pid, visible = wins[0]
u32.ShowWindow(hwnd, 9)          # SW_RESTORE
u32.SetForegroundWindow(hwnd)
time.sleep(0.5)
print("已置前，可见 =", bool(u32.IsWindowVisible(hwnd)))

# ESC: down 0x00, up 0x02
u32.keybd_event(0x1B, 0, 0, 0)
time.sleep(0.05)
u32.keybd_event(0x1B, 0, 2, 0)
print("已发送 ESC")
time.sleep(1.5)

after = find()
print("ESC 后窗口:", [(hex(h), t, v) for h, t, p, v in after])

k32 = ctypes.WinDLL("kernel32")
h = k32.OpenProcess(0x1000, False, pid)
print("进程存活 =", bool(h))
if h:
    k32.CloseHandle(h)
