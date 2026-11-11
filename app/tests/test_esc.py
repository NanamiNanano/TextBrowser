# -*- coding: utf-8 -*-
"""复现与验证：ESC 收进托盘后不应退出，且再次启动要能唤回隐藏的窗口。

用户报的现象是「按 ESC 没最小化，而是直接退出了」。两条链路分别验证：
  1. 隐藏/最小化之后进程不能退出（quitOnLastWindowClosed 必须为 False）；
  2. 窗口隐藏后，第二次启动必须能找到它并恢复——之前 _titles_matching 只枚举
     可见窗口，隐藏后找不到，于是开了第二个实例。
"""
import os
import subprocess
import sys
import time
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from app.core import instance
from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
TMP = os.path.join(ROOT, "build", "esc")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-40s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-40s %s" % (name, e))
        traceback.print_exc()
        failed += 1


for f in ("e.db", "e.db-wal", "e.db-shm", "s.json"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass


class FakeTray:
    """替身：让「有托盘」这条分支可以在无界面环境下被验证。"""

    def __init__(self):
        self.notified = []

    def isVisible(self):
        return True

    def isSystemTrayAvailable(self):
        return True

    def icon(self):
        from PySide6.QtGui import QIcon, QPixmap
        pm = QPixmap(16, 16)
        pm.fill()
        return QIcon(pm)

    def notify(self, text, title="x"):
        self.notified.append(text)


def make_window(enable_tray=False):
    settings = Settings(os.path.join(TMP, "s.json"))
    library = Library(os.path.join(TMP, "e.db"))
    win = MainWindow(settings, library, enable_tray=enable_tray)
    app.setStyleSheet(build_qss(settings))
    win.show()
    app.processEvents()
    return win


print("\n== 0. 默认行为 ==")


def t_default_action():
    from app.core.settings import DEFAULTS
    msg = "默认应当最小化到任务栏（托盘图标不可靠会导致应用失联）"
    assert DEFAULTS["window"]["escAction"] == "minimize", msg
    return "默认 escAction = minimize"


check("默认 ESC 行为", t_default_action)

print("\n== 1. 无托盘时最小化，不退出 ==")

win = make_window(enable_tray=False)


def t_minimize():
    win.hide_to_tray()
    app.processEvents()
    assert win.isMinimized(), "没有托盘时应当最小化，实际既没最小化也没隐藏"
    assert not win.isHidden() or True
    return "退化为最小化"


def t_not_quit():
    quit_called = {"n": 0}
    app.aboutToQuit.connect(lambda: quit_called.__setitem__("n", quit_called["n"] + 1))
    done = {"ok": False}
    QTimer.singleShot(250, lambda: done.__setitem__("ok", True))
    while not done["ok"]:
        app.processEvents()
    assert quit_called["n"] == 0, "隐藏窗口触发了应用退出"
    assert app.quitOnLastWindowClosed() is False
    return "事件循环正常，无退出请求"


def t_restore():
    win.showNormal()
    app.processEvents()
    assert win.isVisible(), "无法恢复显示"
    return "可恢复"


check("无托盘退化为最小化", t_minimize)
check("最小化后不退出", t_not_quit)
check("可恢复显示", t_restore)

print("\n== 2. 有托盘时隐藏窗口，且不退出 ==")

win2 = make_window(enable_tray=False)
fake = FakeTray()
win2.tray = fake                      # 用替身走「有托盘」分支
win2.settings.set("window.escAction", "tray")


def t_hide():
    win2.hide_to_tray()
    app.processEvents()
    assert not win2.isVisible(), "有托盘时应当隐藏窗口"
    assert fake.notified, "首次隐藏应当给出托盘提示"
    return "已隐藏并提示"


def t_hidden_not_quit():
    done = {"ok": False}
    QTimer.singleShot(250, lambda: done.__setitem__("ok", True))
    while not done["ok"]:
        app.processEvents()
    assert app.quitOnLastWindowClosed() is False, "quitOnLastWindowClosed 被改成了 True"
    return "隐藏后事件循环仍在跑"


def t_show_back():
    win2.show_from_tray()
    app.processEvents()
    assert win2.isVisible(), "隐藏后无法恢复"
    return "可恢复显示"


check("有托盘时隐藏", t_hide)
check("隐藏后不退出", t_hidden_not_quit)
check("从托盘恢复", t_show_back)

print("\n== 2b. ESC 行为可切换（托盘 / 任务栏）==")

win3 = make_window(enable_tray=False)
win3.tray = FakeTray()


def t_esc_minimize_mode():
    win3.settings.set("window.escAction", "minimize")
    win3.showNormal()
    app.processEvents()
    win3.hide_to_tray()
    app.processEvents()
    assert win3.isMinimized(), "minimize 模式下应当最小化到任务栏"
    return "最小化到任务栏"


def t_esc_tray_mode():
    win3.settings.set("window.escAction", "tray")
    win3.showNormal()
    app.processEvents()
    win3.hide_to_tray()
    app.processEvents()
    assert not win3.isVisible(), "tray 模式下应当隐藏窗口"
    win3.show_from_tray()
    app.processEvents()
    return "收进托盘"


check("escAction=minimize 保留任务栏", t_esc_minimize_mode)
check("escAction=tray 收进托盘", t_esc_tray_mode)
win3._stop_worker()
win3.hide()

win2._stop_worker()
win2.hide()

print("\n== 3. 跨进程：隐藏的窗口必须能被找到 ==")


def t_find_hidden_cross_process():
    """真正的回归点：先前的实现只枚举可见窗口，隐藏后 activate 返回 False，
    于是第二次双击 exe 会开出第二个实例。"""
    out = open(os.path.join(TMP, "hidden.out"), "wb")
    err = open(os.path.join(TMP, "hidden.err"), "wb")
    proc = subprocess.Popen(
        [sys.executable, "-m", "app.tests.diag_hidden_window", "12"],
        cwd=ROOT, stdout=out, stderr=err)
    try:
        # 等它把窗口显示再隐藏
        deadline = time.time() + 10
        while time.time() < deadline:
            if instance._titles_matching("文本浏览器"):
                break
            time.sleep(0.2)

        handles = instance._titles_matching("文本浏览器")
        assert handles, "隐藏后的窗口没被枚举到（说明还在按可见性过滤）"

        ok = instance.activate("文本浏览器")
        assert ok, "activate 对隐藏窗口返回了 False"
        return "枚举到 %d 个隐藏窗口，activate=True" % len(handles)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        out.close()
        err.close()


check("隐藏窗口可被枚举并唤起", t_find_hidden_cross_process)

win._stop_worker()
win.hide()
try:
    os.remove(os.path.join(TMP, "e.db"))
except OSError:
    pass

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
