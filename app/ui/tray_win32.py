# -*- coding: utf-8 -*-
"""系统托盘（Win32 Shell_NotifyIcon 实现）。

为什么不用 QSystemTrayIcon：
    实测在打包版上 QSystemTrayIcon 静默失败——isVisible() 返回 True、图标对象
    非空、Qt 不打任何告警，但 Windows 通知区域里就是没有。因为 Qt 不把
    Shell_NotifyIcon 的返回值暴露出来，程序无法知道自己到底有没有托盘图标，
    于是「隐藏窗口」就变成了「应用失联」。

    这里直接调 Shell_NotifyIcon，并**用 Shell_NotifyIconGetRect 回查**，
    得到一个明确的布尔值：图标到底注册成功没有、在屏幕什么位置。
    MainWindow 据此决定能不能隐藏窗口。

对外接口刻意与 QSystemTrayIcon 保持一致（show/hide/isVisible/icon/notify/
setToolTip），这样上层代码不用改。
"""
import ctypes
import ctypes.wintypes as wt
import os
import sys

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QPoint, Signal
from PySide6.QtWidgets import QApplication

from .theme import tray_icon

user32 = ctypes.WinDLL("user32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)

WM_APP = 0x8000
CALLBACK_MSG = WM_APP + 1

NIM_ADD, NIM_MODIFY, NIM_DELETE = 0, 1, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP, NIF_INFO = 0x01, 0x02, 0x04, 0x10
NIIF_INFO = 0x01

WM_LBUTTONUP = 0x0202
WM_LBUTTONDBLCLK = 0x0203
WM_RBUTTONUP = 0x0205
WM_CONTEXTMENU = 0x007B

IMAGE_ICON = 1
LR_LOADFROMFILE = 0x10
LR_DEFAULTSIZE = 0x40

S_OK = 0
ERROR_NOT_FOUND = 0x80070490


class NOTIFYICONDATAW(ctypes.Structure):
    """NOTIFYICONDATAW（Vista+）。64 位 sizeof = 976。"""

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


shell32.Shell_NotifyIconW.argtypes = [wt.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
shell32.Shell_NotifyIconW.restype = wt.BOOL
shell32.Shell_NotifyIconGetRect.argtypes = [
    ctypes.POINTER(NOTIFYICONIDENTIFIER), ctypes.POINTER(wt.RECT)]
shell32.Shell_NotifyIconGetRect.restype = ctypes.c_long
user32.LoadImageW.restype = wt.HANDLE
user32.LoadImageW.argtypes = [wt.HINSTANCE, wt.LPCWSTR, wt.UINT,
                              ctypes.c_int, ctypes.c_int, wt.UINT]
user32.DestroyIcon.argtypes = [wt.HICON]


def _icon_path() -> str:
    rel = os.path.join("assets", "app.ico")
    base = getattr(sys, "_MEIPASS", None)
    if base:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, rel)


class _MsgFilter(QAbstractNativeEventFilter):
    def __init__(self, tray):
        super().__init__()
        self.tray = tray

    def nativeEventFilter(self, event_type, message):
        try:
            if event_type == b"windows_generic_MSG" and self.tray._hwnd:
                msg = ctypes.wintypes.MSG.from_address(int(message))
                # 注意是 hWnd（大写 W）：ctypes.wintypes.MSG 的字段名如此，
                # 写成 msg.hwnd 会抛 AttributeError，回调就永远收不到。
                if msg.hWnd and int(msg.hWnd) == self.tray._hwnd and msg.message == CALLBACK_MSG:
                    ev = msg.lParam & 0xFFFF
                    self.tray._on_event(ev)
                    return True, 0
        except Exception:                   # noqa: BLE001
            pass
        return False, 0


class Win32Tray(QObject):
    """壳层与 QSystemTrayIcon 兼容的托盘实现。"""

    sig_show = Signal()
    sig_settings = Signal()
    sig_quit = Signal()
    sig_menu = Signal(QPoint)      # 右键：由主窗口弹出菜单

    def __init__(self, parent=None):
        super().__init__(parent)
        self._added = False
        self._icon_ok = False
        self._hwnd = 0
        self._hicon = None
        self._uid = 1
        self._tooltip = "文本浏览器 —— 双击显示窗口"
        self._data = None
        self._filter = None
        self._rect = None
        self.last_error = None

        ico = _icon_path()
        if os.path.exists(ico):
            self._hicon = user32.LoadImageW(None, ico, IMAGE_ICON, 16, 16, LR_LOADFROMFILE)
        self._icon_ok = bool(self._hicon)
        self._qt_icon = tray_icon()

    # ---------------------------------------------------------- 兼容接口
    def icon(self):
        return self._qt_icon

    def isSystemTrayAvailable(self) -> bool:
        # 只要有 explorer 就认为系统托盘存在；真正的判断在 add() 的返回值
        return bool(user32.FindWindowW("Shell_TrayWnd", None))

    def isVisible(self) -> bool:
        return self._added

    def setToolTip(self, text: str) -> None:
        self._tooltip = text
        if self._added:
            self._data.szTip = text
            self._data.uFlags = NIF_TIP
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data))

    def toolTip(self) -> str:
        return self._tooltip

    # ---------------------------------------------------------- 生命周期
    def attach(self, window) -> bool:
        """把托盘挂到某个窗口上（用它的 HWND 接收回调），并注册图标。"""
        self._hwnd = int(window.winId())
        self._data = NOTIFYICONDATAW()
        self._data.cbSize = ctypes.sizeof(NOTIFYICONDATAW)
        self._data.hWnd = self._hwnd
        self._data.uID = self._uid
        self._data.uFlags = NIF_MESSAGE | NIF_ICON | NIF_TIP
        self._data.uCallbackMessage = CALLBACK_MSG
        self._data.hIcon = self._hicon
        self._data.szTip = self._tooltip

        if self._filter is None:
            self._filter = _MsgFilter(self)
            app = QApplication.instance()
            if app is not None:
                app.installNativeEventFilter(self._filter)

        ok = bool(shell32.Shell_NotifyIconW(NIM_ADD, ctypes.byref(self._data)))
        self.last_error = ctypes.get_last_error()
        self._added = ok
        if ok:
            self._rect = self.query_rect()
        return ok

    def show(self) -> None:
        if not self._added:
            self.attach(self._parent_window())

    def hide(self) -> None:
        if self._added and self._data is not None:
            shell32.Shell_NotifyIconW(NIM_DELETE, ctypes.byref(self._data))
            self._added = False

    def _parent_window(self):
        return self.parent()

    def query_rect(self):
        """回查图标在屏幕上的位置。返回 QRect 或 None（None = 系统里没有）。"""
        if not self._hwnd:
            return None
        ident = NOTIFYICONIDENTIFIER()
        ident.cbSize = ctypes.sizeof(NOTIFYICONIDENTIFIER)
        ident.hWnd = self._hwnd
        ident.uID = self._uid
        r = wt.RECT()
        hr = shell32.Shell_NotifyIconGetRect(ctypes.byref(ident), ctypes.byref(r))
        if hr & 0xFFFFFFFF == S_OK:
            from PySide6.QtCore import QRect
            return QRect(r.left, r.top, r.right - r.left, r.bottom - r.top)
        return None

    def notify(self, text: str, title: str = "文本浏览器") -> None:
        """气泡提示（走 NIF_INFO）。失败就算了，不弹模态框打扰用户。"""
        if not self._added:
            return
        try:
            self._data.uFlags = NIF_INFO
            self._data.szInfoTitle = title
            self._data.szInfo = text
            self._data.dwInfoFlags = NIIF_INFO
            shell32.Shell_NotifyIconW(NIM_MODIFY, ctypes.byref(self._data))
        except Exception:                   # noqa: BLE001
            pass

    # ---------------------------------------------------------- 事件
    def _on_event(self, ev: int) -> None:
        if ev in (WM_LBUTTONUP, WM_LBUTTONDBLCLK):
            self.sig_show.emit()
        elif ev in (WM_RBUTTONUP, WM_CONTEXTMENU):
            from PySide6.QtGui import QCursor
            self.sig_menu.emit(QCursor.pos())
