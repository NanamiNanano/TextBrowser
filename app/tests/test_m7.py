# -*- coding: utf-8 -*-
"""M7 测试：滚轮翻页、右键菜单、背景透明（文字不透明）。"""
import os
import sys
import traceback

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QWheelEvent
from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import Settings
from app.ui.main_window import MainWindow
from app.ui.theme import bg_alpha, build_qss, qss_color

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "m7")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])
app.setQuitOnLastWindowClosed(False)

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-34s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-34s %s" % (name, e))
        traceback.print_exc()
        failed += 1


for f in ("m.db", "m.db-wal", "m.db-shm", "s.json"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass

settings = Settings(os.path.join(TMP, "s.json"))
library = Library(os.path.join(TMP, "m.db"))
bid = library.add_file(BIG)
assert bid, "语料缺失"

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.resize(1000, 760)
win.show()
app.processEvents()
win.open_book(bid)
app.processEvents()
win._stop_worker()
reader = win.reader


def wheel(dy):
    ev = QWheelEvent(QPointF(200, 200), QPointF(200, 200), QPoint(0, 0), QPoint(0, dy),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                     Qt.ScrollPhase.NoScrollPhase, False)
    reader.wheelEvent(ev)
    app.processEvents()


print("\n== 1. 滚轮翻页 ==")


def t_wheel_down():
    reader.goto_offset(0)
    wheel(120)
    base = reader.page_number()
    wheel(-120)
    assert reader.page_number() == base + 1, "向下滚一格没有翻到下一页"
    return "%d -> %d" % (base, base + 1)


def t_wheel_up():
    cur = reader.page_number()
    wheel(120)
    assert reader.page_number() == cur - 1, "向上滚一格没有回到上一页"
    return "%d -> %d" % (cur, cur - 1)


def t_wheel_accumulate():
    cur = reader.page_number()
    wheel(-40)
    wheel(-40)
    assert reader.page_number() == cur, "不足一格就翻页了（手滑会狂翻）"
    wheel(-40)                       # 累计 120
    assert reader.page_number() == cur + 1, "累计满一格没翻页"
    return "40+40+40 = 一格"


def t_wheel_scroll_mode():
    win.toggle_reading_mode()
    app.processEvents()
    before = reader.top_offset()
    wheel(-120)
    moved = reader.top_offset() != before
    win.toggle_reading_mode()
    app.processEvents()
    assert moved, "滚动模式下滚轮没动"
    return "滚动模式仍为滚动"


check("向下滚一格翻一页", t_wheel_down)
check("向上滚一格回一页", t_wheel_up)
check("累积满一格才翻", t_wheel_accumulate)
check("滚动模式不翻页", t_wheel_scroll_mode)

print("\n== 2. 右键菜单 ==")


def t_menu_items():
    menu = win._build_reader_menu()
    texts = [a.text() for a in menu.actions() if not a.isSeparator()]
    need = ["目录", "搜索", "书签栏", "在当前位置添加书签",
            "切换分页 / 滚动", "偏好设置…", "复制本页文字", "回到书架"]
    missing = [t for t in need if t not in texts]
    assert not missing, "缺少菜单项: %s" % missing
    return "%d 项" % len(texts)


def t_menu_actions_work():
    win.close_side()
    app.processEvents()
    menu = win._build_reader_menu()
    act = [a for a in menu.actions() if a.text() == "目录"][0]
    act.trigger()
    app.processEvents()
    ok = win.side.isVisible() and win.side.currentWidget() is win.toc
    win.close_side()
    app.processEvents()
    assert ok, "点「目录」没打开目录栏"
    return "目录项可用"


def t_menu_copy_state():
    """复制本页文字：按钮可用，且点了真的进剪贴板。"""
    QApplication.clipboard().setText("")
    menu = win._build_reader_menu()
    act = [a for a in menu.actions() if a.text() == "复制本页文字"][0]
    assert act.isEnabled(), "有书打开时复制项应当可用"
    act.trigger()
    app.processEvents()
    got = QApplication.clipboard().text()
    assert got and len(got) > 20, "剪贴板没拿到本页文字"
    return "复制了 %d 字" % len(got)


check("菜单项齐全", t_menu_items)
check("菜单动作生效", t_menu_actions_work)
check("复制项状态", t_menu_copy_state)

print("\n== 3. 背景透明、文字不透明 ==")


def t_qss_color():
    assert qss_color("#F5EFE0", 1.0) == "#F5EFE0", "不透明时不该改写法"
    got = qss_color("#F5EFE0", 0.5)
    assert got.startswith("rgba(") and got.endswith(",128)"), got
    return got


def t_alpha_default():
    assert bg_alpha(settings) == 1.0, "默认应为完全不透明"
    return "默认 1.0"


def _render(alpha):
    settings.set("appearance.bgOpacity", alpha)
    win.apply_theme()
    win.apply_opacity()
    win.repaint()
    app.processEvents()
    img = QImage(win.size(), QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    win.render(p, QPoint(0, 0))
    p.end()
    return img


def t_bg_translucent_text_opaque():
    img = _render(0.55)
    bg = img.pixelColor(60, 420)
    assert bg.alpha() < 200, "背景没有变透明: alpha=%d" % bg.alpha()

    # 统计 alpha 分布：应当同时存在「半透明背景」和「完全不透明的文字」
    alphas = {}
    for y in range(0, img.height(), 3):
        for x in range(0, img.width(), 3):
            a = img.pixelColor(x, y).alpha()
            alphas[a] = alphas.get(a, 0) + 1
    has_translucent = any(100 <= a <= 200 for a in alphas)
    has_opaque = alphas.get(255, 0) > 100
    assert has_translucent, "没找到半透明背景像素"
    assert has_opaque, "文字也一起变透明了（这正是不想要的）"
    return "背景 alpha=%d，不透明像素 %d 个" % (bg.alpha(), alphas.get(255, 0))


def t_window_opacity_untouched():
    assert abs(win.windowOpacity() - 1.0) < 0.01, \
        "仍在用整窗透明度（会把文字一起弄淡）"
    return "windowOpacity=%.2f" % win.windowOpacity()


def t_full_opaque_restore():
    img = _render(1.0)
    bg = img.pixelColor(60, 420)
    assert bg.alpha() == 255, "100%% 时背景应当不透明: %d" % bg.alpha()
    return "100% 时不透明"


check("qss 颜色转换", t_qss_color)
check("默认不透明", t_alpha_default)
check("背景透、文字不透", t_bg_translucent_text_opaque)
check("不再用整窗透明度", t_window_opacity_untouched)
check("100% 恢复不透明", t_full_opaque_restore)

win._stop_worker()
win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
