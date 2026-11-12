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
