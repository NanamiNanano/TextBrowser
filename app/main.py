# -*- coding: utf-8 -*-
"""程序入口。"""
import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from .config import APP_DISPLAY_NAME, APP_VERSION, DATA_DIR
from .core import instance
from .core.library import Library
from .core.settings import Settings
from .ui.main_window import MainWindow
from .ui.theme import app_icon, build_qss

INSTANCE_KEY = "TextBrowser-SingleInstance-v1"
POLL_MS = 800


def _install_excepthook() -> None:
    """把未捕获异常写进日志，而不是让进程静默消失。

    PySide6 里槽函数抛异常时，窗口模式下没有控制台，用户只会看到「程序自己退了」。
    这里挂一个 hook：记日志 + 保留进程，方便定位。
    """
    import datetime
    import traceback

    log_dir = os.path.join(DATA_DIR, "logs")
    try:
        os.makedirs(log_dir, exist_ok=True)
    except OSError:
        log_dir = None

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            if log_dir:
                path = os.path.join(log_dir, "crash-%s.log" % datetime.date.today())
                with open(path, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
        except OSError:
            pass
        try:
            sys.stderr.write(text)
        except Exception:                       # noqa: BLE001
            pass

    sys.excepthook = hook


def main(argv=None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    files = [os.path.abspath(a) for a in argv[1:] if os.path.isfile(a)]
    debug = os.environ.get("TB_DEBUG_INSTANCE")
    _install_excepthook()

    # 已有实例：优先唤醒它；唤不到说明占着名字的是残留内核对象，换备用名字继续启动
    if not instance.acquire(INSTANCE_KEY):
        if files:
            instance.write_open_request(DATA_DIR, files)
        activated = instance.activate(APP_DISPLAY_NAME)
        if debug:
            print("[main] 已有同名实例，activate ->", activated, file=sys.stderr)
        if activated:
            return 0
        fallback = instance.acquire(INSTANCE_KEY + "-fallback")
        if debug:
            print("[main] 备用名字 acquire ->", fallback, file=sys.stderr)
        if not fallback:
            return 0

    app = QApplication(argv)
    app.setApplicationName("TextBrowser")
    app.setApplicationDisplayName(APP_DISPLAY_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setOrganizationName("TextBrowser")
    app.setQuitOnLastWindowClosed(False)      # 托盘常驻：关窗口不等于退出
    app.setWindowIcon(app_icon())

    font = QFont("Microsoft YaHei")
    font.setPixelSize(13)
    app.setFont(font)

    settings = Settings()
    library = Library()

    win = MainWindow(settings, library)
    app.setStyleSheet(build_qss(settings))
    win.show()

    # 退出前必须让后台识别线程收尾，否则 QThread 会在运行中被析构
    app.aboutToQuit.connect(win._stop_worker)

    def open_files(paths):
        if not paths:
            return
        win.shelf.import_paths(paths)
        books = library.list_books()
        if books:
            win.open_book(int(books[0]["id"]))

    if files:
        open_files(files)

    # 轮询第二实例留下的待打开请求（命名管道不可用，用文件传递）。
    # 初始 stamp 取当前文件的时间戳：程序启动前遗留的请求不该被重复执行，
    # 否则上次没处理完的文件会在每次开机时被强制打开。
    state = {"stamp": instance.read_open_request(DATA_DIR)[1]}

    def poll():
        paths, stamp = instance.read_open_request(DATA_DIR)
        if stamp and stamp != state["stamp"]:
            state["stamp"] = stamp
            win.show_from_tray()
            open_files(paths)

    timer = QTimer()
    timer.timeout.connect(poll)
    timer.start(POLL_MS)
    app._open_poll_timer = timer

    rc = app.exec()
    library.close()
    return rc


if __name__ == "__main__":
    sys.exit(main())
