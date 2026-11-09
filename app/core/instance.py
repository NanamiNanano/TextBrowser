# -*- coding: utf-8 -*-
"""单实例与「唤起已有窗口」。

**为什么不用 QLocalServer/QLocalSocket**：它们底层是 Windows 命名管道，
在受限环境下会被拒绝（实测 `listen()` 直接返回 False、`errorString()` 为
「拒绝访问」），单实例会静默失效——用户双击两次就看到两个窗口。

这里改用纯 Win32：
  * `CreateMutexW` 判断是否已有实例（内核对象，不走管道）；
  * `EnumWindows` 按窗口标题前缀找到已有窗口，`ShowWindow` + `SetForegroundWindow` 唤起。
"""
import ctypes
import ctypes.wintypes as wt
import os

ERROR_ALREADY_EXISTS = 183
SW_RESTORE = 9
SW_SHOW = 5
SW_MINIMIZE = 6

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)
_u32 = ctypes.WinDLL("user32", use_last_error=True)

_k32.CreateMutexW.restype = wt.HANDLE
_k32.CreateMutexW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.LPCWSTR]
_u32.EnumWindows.restype = wt.BOOL
_u32.IsWindowVisible.argtypes = [wt.HWND]
_u32.GetWindowTextLengthW.argtypes = [wt.HWND]
_u32.GetWindowTextW.argtypes = [wt.HWND, wt.LPWSTR, ctypes.c_int]
_u32.ShowWindow.argtypes = [wt.HWND, ctypes.c_int]
_u32.SetForegroundWindow.argtypes = [wt.HWND]
_u32.IsIconic.argtypes = [wt.HWND]
_u32.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]

_ENUMPROC = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)

# 句柄必须保活到进程结束，否则互斥体被销毁、单实例失效
_mutex_handle = None


def acquire(name: str) -> bool:
    """尝试成为唯一实例。返回 True 表示本次是第一个实例。"""
    global _mutex_handle
    try:
        h = _k32.CreateMutexW(None, False, name)
        err = ctypes.get_last_error()
        if not h:
            return True                      # 拿不到就用，不要因此阻止启动
        if err == ERROR_ALREADY_EXISTS:
            _k32.CloseHandle(h)
            return False
        _mutex_handle = h
        return True
    except OSError:
        return True


def _titles_matching(prefix: str):
    """枚举所有可见窗口，返回标题以 prefix 开头的窗口句柄（排除本进程自己的）。"""
    me = os.getpid()
    out = []

    def _cb(hwnd, _lp):
        if not _u32.IsWindowVisible(hwnd):
            return True
        n = _u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return True
        buf = ctypes.create_unicode_buffer(n + 1)
        _u32.GetWindowTextW(hwnd, buf, n + 1)
        title = buf.value or ""
        if not title.startswith(prefix):
            return True
        pid = wt.DWORD(0)
        _u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == me:
            return True
        out.append(hwnd)
        return True

    _u32.EnumWindows(_ENUMPROC(_cb), 0)
    return out


def activate(prefix: str) -> bool:
    """把已有的主窗口恢复并置前。找到并成功唤起返回 True。"""
    handles = _titles_matching(prefix)
    if not handles:
        return False

    hwnd = handles[0]
    if _u32.IsIconic(hwnd):
        _u32.ShowWindow(hwnd, SW_RESTORE)
    else:
        _u32.ShowWindow(hwnd, SW_SHOW)

    # SetForegroundWindow 受前台锁定限制，失败时把窗口提到顶层并闪任务栏按钮，
    # 至少让用户看到窗口在哪。
    if not _u32.SetForegroundWindow(hwnd):
        try:
            _u32.BringWindowToTop(hwnd)
            _u32.FlashWindow(hwnd, True)
        except AttributeError:
            pass
    return True


# ---------------------------------------------------------------- 待打开文件
# 第二实例想把文件交给已有实例，但命名管道不可用，改用「落一个请求文件」：
# 请求方写 JSON，已有实例定时轮询；以 mtime 去重，避免重复打开同一个文件。
_OPEN_REQUEST_NAME = "pending_open.json"


def write_open_request(data_dir: str, paths) -> bool:
    import json
    import time
    try:
        os.makedirs(data_dir, exist_ok=True)
        payload = {"paths": [os.path.abspath(p) for p in paths], "ts": time.time()}
        with open(os.path.join(data_dir, _OPEN_REQUEST_NAME), "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except OSError:
        return False


def read_open_request(data_dir: str):
    """返回 (paths, stamp)。stamp 相同表示没有新请求。"""
    import json
    path = os.path.join(data_dir, _OPEN_REQUEST_NAME)
    try:
        st = os.stat(path)
    except OSError:
        return [], 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        paths = [p for p in payload.get("paths", []) if isinstance(p, str)]
        return paths, st.st_mtime_ns
    except (OSError, ValueError):
        return [], st.st_mtime_ns

