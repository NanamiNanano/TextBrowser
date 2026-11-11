# -*- coding: utf-8 -*-
"""复现「按 ESC 没最小化而是退出」。

做法：找到打包版主窗口 → 置前 → 用 SendInput 真实按一下 ESC → 观察
窗口是否隐藏、进程是否存活。
"""
import ctypes
import ctypes.wintypes as wt
import sys
import time

u32 = ctypes.WinDLL("user32", use_last_error=True)
k32 = ctypes.WinDLL("kernel32")

u32.EnumWindows.restype = wt.BOOL
u32.GetWindowTextLengthW.argtypes = [wt.HWND]
u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
u32.IsWindowVisible.argtypes = [wt.HWND]
u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
u32.SetForegroundWindow.argtypes = [wt.HWND]
u32.SetFocus.argtypes = [wt.HWND]
u32.PostMessageW.argtypes = [wt.HWND, wt.UINT, wt.WPARAM, wt.LPARAM]
u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
u32.IsIconic.argtypes = [wt.HWND]

ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_window(prefix="文本浏览器"):
    found = []

    def cb(hwnd, _lp):
        n = u32.GetWindowTextLengthW(hwnd)
        if n > 0 and u32.IsWindowVisible(hwnd):
            buf = ctypes.create_unicode_buffer(n + 1)
            u32.GetWindowTextW(hwnd, buf, n + 1)
            if buf.value.startswith(prefix):
                pid = wt.DWORD(0)
                u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                found.append((hwnd, buf.value, pid.value))
        return True

    u32.EnumWindows(ENUMPROC(cb), 0)
    return found


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wt.WORD), ("wScan", wt.WORD), ("dwFlags", wt.DWORD),
                ("time", wt.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("pad", ctypes.c_byte * 24)]
    _anonymous_ = ("u",)
    _fields_ = [("type", wt.DWORD), ("u", _U)]


def send_esc():
    u32.SendInput.argtypes = [wt.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
    inputs = (INPUT * 2)()
    for i, flags in enumerate((0, 2)):          # 0=按下, 2=抬起
        inputs[i].type = 1                       # INPUT_KEYBOARD
        inputs[i].ki.wVk = 0x1B                  # VK_ESCAPE
        inputs[i].ki.dwFlags = flags
    n = u32.SendInput(2, inputs, ctypes.sizeof(INPUT))
    return n


def main():
    wins = find_window()
    print("可见窗口:", [(hex(h), t) for h, t, _ in wins])
    if not wins:
        print("没找到主窗口")
        return 1

    hwnd, title, pid = wins[0]
    print("目标窗口: %s  pid=%d  标题=%r" % (hex(hwnd), pid, title))

    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
    time.sleep(0.6)
    print("置前后可见:", bool(u32.IsWindowVisible(hwnd)))

    n = send_esc()
    print("SendInput 发送事件数:", n)
    time.sleep(1.5)

    visible = bool(u32.IsWindowVisible(hwnd))
    minimized = bool(u32.IsIconic(hwnd))
    still = find_window()
    print("ESC 之后:")
    print("  窗口可见 =", visible, " 最小化 =", minimized)
    print("  还能枚举到的主窗口:", [(hex(h), t) for h, t, _ in still])

    h = k32.OpenProcess(0x1000, False, pid)
    alive = bool(h)
    if h:
        k32.CloseHandle(h)
    print("  进程存活 =", alive)
    return 0


if __name__ == "__main__":
    sys.exit(main())
