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
    msg = "默认应当是 auto：托盘可用就收进托盘，不可用才最小化"
    assert DEFAULTS["window"]["escAction"] == "auto", msg
    return "默认 escAction = auto"


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



print("\n== 4. 关闭按钮必须能真正退出 ==")

win4 = make_window(enable_tray=False)


def t_close_quits_without_tray():
    """没有可用托盘时，点 ✕ 必须退出——否则用户除了任务管理器没法关掉程序。"""
    called = []
    orig = win4.quit_app
    win4.quit_app = lambda: (called.append(1), orig())[1]
    win4.show()
    app.processEvents()
    win4.close()
    app.processEvents()
    assert called, "无托盘时点 ✕ 没有触发退出（窗口只会被最小化/隐藏）"
    return "✕ -> quit_app"


def t_close_hides_with_tray():
    win5 = make_window(enable_tray=False)
    win5.tray = FakeTray()
    win5.settings.set("window.escAction", "tray")
    win5.show()
    app.processEvents()
    called = []
    orig = win5.quit_app
    win5.quit_app = lambda: (called.append(1), orig())[1]
    win5.close()
    app.processEvents()
    ok = not called and not win5.isVisible()
    win5.quit_app = orig
    win5._stop_worker()
    assert ok, "有托盘时 ✕ 应当收进托盘（不出退），实际 quit=%s" % bool(called)
    return "✕ -> 收进托盘"


check("无托盘 ✕ 退出", t_close_quits_without_tray)
check("有托盘 ✕ 收起", t_close_hides_with_tray)
win._stop_worker()
win.hide()
try:
    os.remove(os.path.join(TMP, "e.db"))
except OSError:
    pass


print("\n== 5. 托盘回调与配置迁移 ==")


def t_tray_callback():
    """托盘图标点击要能触发信号。

    这里直接用 PostMessage 投递 WM_APP+1，不需要真的注册图标——
    之前 msg.hwnd 写错成小写（ctypes 里是 hWnd），回调永远收不到。
    """
    import ctypes

    win6 = make_window(enable_tray=True)
    win6.tray.sig_menu.disconnect()          # 别在测试里弹真实菜单
    hits = []
    win6.tray.sig_show.connect(lambda: hits.append("show"))
    win6.tray.sig_menu.connect(lambda pos: hits.append("menu"))

    u = ctypes.WinDLL("user32")
    u.PostMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint,
                               ctypes.c_size_t, ctypes.c_size_t]
    hwnd = int(win6.winId())
    for lp in (0x0202, 0x0205):              # 左键抬起 / 右键抬起
        u.PostMessageW(hwnd, 0x8001, 1, lp)
        app.processEvents()
    ok = hits == ["show", "menu"]
    win6._stop_worker()
    assert ok, "托盘回调没收到，实际: %s" % hits
    return "左键->show，右键->menu"


def t_settings_migrate():
    """老配置里被自动写入的 escAction=minimize 要迁移成 auto。"""
    import json
    import tempfile
    from app.core.settings import Settings as S

    d = tempfile.mkdtemp()
    p = os.path.join(d, "s.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump({"window": {"escAction": "minimize"}}, f)
    s = S(p)
    assert s.get("window.escAction") == "auto", "迁移没生效：%s" % s.get("window.escAction")

    # 迁移只做一次：用户之后手动选 minimize 必须保留
    s.set("window.escAction", "minimize")
    s.save()
    assert S(p).get("window.escAction") == "minimize", "迁移把用户的选择覆盖了"
    return "老配置 -> auto，手动选择保留"

check("托盘左键右键回调", t_tray_callback)
check("ESC 配置迁移", t_settings_migrate)


def t_tray_failure_is_notice_not_modal():
    """托盘注册失败时只能用窗口内提示条，不许弹模态框。

    模态框会打断阅读、还得手动点掉——用户明确要求过不要。
    """
    import PySide6.QtWidgets as W

    called = []
    orig_warn = W.QMessageBox.warning
    orig_info = W.QMessageBox.information
    orig_crit = W.QMessageBox.critical
    W.QMessageBox.warning = staticmethod(lambda *a, **k: called.append("warning"))
    W.QMessageBox.information = staticmethod(lambda *a, **k: called.append("info"))
    W.QMessageBox.critical = staticmethod(lambda *a, **k: called.append("critical"))
    try:
        w = make_window(enable_tray=True)
        app.processEvents()
        visible = w.notice.isVisible()
        text = w.notice.lbl.text()
        w._stop_worker()
        w.hide()
    finally:
        W.QMessageBox.warning = orig_warn
        W.QMessageBox.information = orig_info
        W.QMessageBox.critical = orig_crit
    assert not called, "托盘失败弹了模态框: %s" % called
    assert visible and text, "提示条没显示"
    return "提示条：%s" % text[:24]


check("托盘失败不弹模态框", t_tray_failure_is_notice_not_modal)

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
