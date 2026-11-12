# -*- coding: utf-8 -*-
"""诊断输出：写文件 / 截任务栏通知区域。

这些只在排查打包版「托盘没有图标」时用，通过环境变量开启：
    TB_DEBUG_DIR=<目录>        指定输出目录（默认依次尝试 exe 目录、数据目录）
    TB_DEBUG_TRAYSHOT=1        启动 2.5 秒后截图任务栏通知区域
    TB_DEBUG_ICON=1            把生成的 64px 托盘图标存成 PNG
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys


def output_dir() -> str:
    """找一个确定可写的位置：优先环境变量，其次 exe 所在目录，最后数据目录。"""
    cand = []
    env = os.environ.get("TB_DEBUG_DIR")
    if env:
        cand.append(env)
    if getattr(sys, "frozen", False):
        cand.append(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        cand.append(os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)))))
    try:
        from .config import DATA_DIR
        cand.append(os.path.join(DATA_DIR, "logs"))
    except Exception:                       # noqa: BLE001
        pass

    for d in cand:
        try:
            os.makedirs(d, exist_ok=True)
            probe = os.path.join(d, ".tb_write_probe")
            with open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except OSError:
            continue
    return os.getcwd()


_PATH = None


def path(name: str) -> str:
    global _PATH
    if _PATH is None:
        _PATH = output_dir()
    return os.path.join(_PATH, name)


def write(name: str, text: str) -> None:
    try:
        with open(path(name), "a", encoding="utf-8") as f:
            f.write(text.rstrip("\n") + "\n")
    except OSError:
        pass


class NOTIFYICONDATAW(ctypes.Structure):
    """NOTIFYICONDATAW（Vista 及以后）。64 位下 sizeof 应为 976。"""

    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("uFlags", wt.UINT),
        ("uCallbackMessage", wt.UINT),
        ("hIcon", wt.HICON),
        ("szTip", wt.WCHAR * 128),
        ("dwState", wt.DWORD),
        ("dwStateMask", wt.DWORD),
        ("szInfo", wt.WCHAR * 256),
        ("uVersion", wt.UINT),
        ("szInfoTitle", wt.WCHAR * 64),
        ("dwInfoFlags", wt.DWORD),
        ("guidItem", ctypes.c_byte * 16),
        ("hBalloonIcon", wt.HICON),
    ]


class NOTIFYICONIDENTIFIER(ctypes.Structure):
    _fields_ = [
        ("cbSize", wt.DWORD),
        ("hWnd", wt.HWND),
        ("uID", wt.UINT),
        ("guidItem", ctypes.c_byte * 16),
    ]


def _icon_file() -> str:
    rel = os.path.join("assets", "app.ico")
    base = getattr(sys, "_MEIPASS", None)
    if base and os.path.exists(os.path.join(base, rel)):
        return os.path.join(base, rel)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, rel)


def probe_tray(hwnd: int) -> None:
    """向 Windows 直接注册一个探针图标，再查询它的位置。

    Shell_NotifyIcon 的返回值 + Shell_NotifyIconGetRect 的结果是**客观的**：
    能查到矩形就说明通知区域真的收下了这个图标；ERROR_NOT_FOUND 则说明没收。
    这样就不需要人肉盯着任务栏看。
    """
    shell32 = ctypes.WinDLL("shell32")
    u32 = ctypes.WinDLL("user32")
    shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    shell32.Shell_NotifyIconW.restype = wt.BOOL
    shell32.Shell_NotifyIconGetRect.argtypes = [
        ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wt.RECT)]
    shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
    u32.LoadImageW.restype = wt.HANDLE
    u32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                               ctypes.c_int, ctypes.c_int, wt.UINT]

    write("tray_diag.txt", "== probe_tray ==")
    write("tray_diag.txt", "sizeof(NOTIFYICONDATAW) = %d (期望 976)"
          % ctypes.sizeof(NOTIFYICONDATAW))
    write("tray_diag.txt", "sizeof(NOTIFYICONIDENTIFIER) = %d"
          % ctypes.sizeof(NOTIFYICONIDENTIFIER))

    ico = _icon_file()
    write("tray_diag.txt", "icon 文件: %s 存在=%s" % (ico, os.path.exists(ico)))
    IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x10, 0x40
    hicon = u32.LoadImageW(None, ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
    write("tray_diag.txt", "LoadImage hicon=%s err=%d"
          % (hicon, ctypes.get_last_error()))

    NIM_ADD, NIM_DELETE = 0, 2
    NIF_MESSAGE, NIF_ICON, NIF_TIP = 0x1, 0x2, 0x4
    uid = 0x5A5A
    data = NOTIFYICONDATAW()
    data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
    data.hWnd = hwnd
    data.uID = uid
    data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
    data.uCallbackMessage = 0x8000 + 1
    data.hIcon = hicon
    data.szTip = "文本浏览器 探针"

    ok = shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(data))
    write("tray_diag.txt", "Shell_NotifyIcon(NIM_ADD) -> %s err=%d"
          % (bool(ok), ctypes.get_last_error()))

    if ok:
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = hwnd
        ident.uID = uid
        rect = wt.RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(rect))
        # S_OK = 0；0x80070490 = ERROR_NOT_FOUND
        write("tray_diag.txt", "Shell_NotifyIconGetRect -> hr=0x%08X rect=(%d,%d,%d,%d)"
              % (hr & 0xFFFFFFFF, rect.left, rect.top, rect.right, rect.bottom))
        if hr == 0:
            from PySide6.QtGui import QGuiApplication
            vis = QGuiApplication.primaryScreen().availableGeometry()
            inside = (vis.left() <= rect.left and rect.right <= vis.right()
                      and vis.top() <= rect.top and rect.bottom <= vis.bottom())
            write("tray_diag.txt", "  -> 图标已注册；在屏幕可见区=%s（False 通常表示在 ^ 溢出区）"
                  % inside)
        shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(data))
        write("tray_diag.txt", "探针已删除")


def screenshot_tray(prefix: str = "tray_area") -> None:
    """把任务栏通知区域（含溢出区）截图存盘，用来肉眼确认图标在不在。"""
    from PySide6.QtGui import QGuiApplication

    u32 = ctypes.WinDLL("user32")
    u32.FindWindowW.restype = wt.HWND
    u32.GetWindowRect.argtypes = [wt.HWND, ctypes.POINTER(wt.RECT)]

    write("tray_diag.txt", "== screenshot_tray 开始 ==")
    for name in ("Shell_TrayWnd", "NotifyIconOverflowWindow"):
        hwnd = u32.FindWindowW(name, None)
        write("tray_diag.txt", "%s hwnd=%s" % (name, hwnd))
        if not hwnd:
            continue
        r = wt.RECT()
        if not u32.GetWindowRect(hwnd, ctypes.byref(r)):
            write("tray_diag.txt", "GetWindowRect 失败")
            continue
        w = r.right - r.left
        h = r.bottom - r.top
        write("tray_diag.txt", "  rect=(%d,%d,%dx%d)" % (r.left, r.top, w, h))
        for i, screen in enumerate(QGuiApplication.screens()):
            pm = screen.grabWindow(0, r.left, r.top, w, h)
            out = path("%s_%s_%d.png" % (prefix, name, i))
            ok = pm.save(out, "PNG")
            write("tray_diag.txt", "  保存 %s -> %s (%dx%d)"
                  % (out, ok, pm.width(), pm.height()))
