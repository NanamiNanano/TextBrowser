# -*- coding: utf-8 -*-
"""M3 测试：设置面板、预设主题、屏幕取色器。

取色器不依赖真实屏幕：注入一张已知像素的合成图，直接验证“逻辑坐标 ->
设备像素”的映射与颜色采样是否正确。这条链路最容易在 DPI 缩放上出错。
"""
import os
import sys
import traceback

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtGui import QColor, QImage, QMouseEvent
from PySide6.QtWidgets import QApplication

from app.core.library import Library
from app.core.settings import PRESETS, Settings
from app.ui.eyedropper import Eyedropper
from app.ui.main_window import MainWindow
from app.ui.theme import build_qss, is_dark, mix

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIG = os.path.join(ROOT, "spike", "corpus", "big_100mb.txt")
TMP = os.path.join(ROOT, "build", "m3")
os.makedirs(TMP, exist_ok=True)

app = QApplication.instance() or QApplication([])

passed = failed = 0


def check(name, fn):
    global passed, failed
    try:
        detail = fn()
        print("  PASS  %-36s %s" % (name, detail or ""))
        passed += 1
    except Exception as e:
        print("  FAIL  %-36s %s" % (name, e))
        traceback.print_exc()
        failed += 1


for f in ("m3.db", "m3.db-wal", "m3.db-shm", "s.json"):
    try:
        os.remove(os.path.join(TMP, f))
    except OSError:
        pass

settings = Settings(os.path.join(TMP, "s.json"))
library = Library(os.path.join(TMP, "m3.db"))
bid = library.add_file(BIG)

win = MainWindow(settings, library, enable_tray=False)
app.setStyleSheet(build_qss(settings))
win.show()
win.resize(1120, 780)
app.processEvents()
win.open_book(bid)
app.processEvents()
win._stop_worker()

print("\n== 1. 设置面板 ==")


def t_open():
    win.open_settings()
    app.processEvents()
    d = win._settings_dlg
    assert d is not None and d.isVisible(), "设置面板没有打开"
    assert d.spn_size.value() == int(settings.get("appearance.fontSize")), "字号控件没同步"
    assert d.cmb_mode.currentData() == settings.get("reading.mode"), "模式控件没同步"
    return "打开并同步初值（字号 %d）" % d.spn_size.value()


def t_change_font_size():
    d = win._settings_dlg
    d.spn_size.setValue(30)
    app.processEvents()
    assert settings.get("appearance.fontSize") == 30, "设置没写回"
    assert win.reader.pg.layout.font_px == 30, "阅读器没有重新排版（font_px=%d）" % win.reader.pg.layout.font_px
    assert win.reader.pg.doc.toPlainText().strip(), "改字号后正文没了"
    d.spn_size.setValue(20)
    app.processEvents()
    return "字号 30 生效并重排，正文仍可读"


def t_change_line_height():
    d = win._settings_dlg
    d.spn_line.setValue(2.2)
    app.processEvents()
    assert abs(win.reader.pg.layout.line_height - 2.2) < 0.01
    assert win.reader.pg.doc.toPlainText().strip()
    d.spn_line.setValue(1.8)
    app.processEvents()
    return "行距 2.2 生效"


def t_preset():
    d = win._settings_dlg
    for p in PRESETS:
        d._apply_preset(p)
        app.processEvents()
        assert settings.get("appearance.bgColor") == p["bg"], "预设背景没应用"
        assert settings.get("appearance.textColor") == p["fg"]
        assert win.reader.pg.doc.toPlainText().strip(), "预设后正文没了"
    d._apply_preset(PRESETS[0])
    app.processEvents()
    return "5 套预设全部生效"


def t_mode_switch():
    d = win._settings_dlg
    d.cmb_mode.setCurrentIndex(1)          # 连续滚动
    app.processEvents()
    assert settings.get("reading.mode") == "scroll"
    assert win.reader.is_scroll_mode(), "阅读器没切到滚动模式"
    d.cmb_mode.setCurrentIndex(0)
    app.processEvents()
    assert not win.reader.is_scroll_mode(), "没切回分页"
    return "设置面板切模式能带动阅读器"


def t_contrast():
    d = win._settings_dlg
    d._apply_preset({"bg": "#FFFFFF", "fg": "#111111"})
    app.processEvents()
    text = d.lbl_contrast.text()
    assert "对比度" in text and "偏低" not in text, "高对比配色被误判：%s" % text
    d._apply_preset({"bg": "#888888", "fg": "#999999"})
    app.processEvents()
    low = d.lbl_contrast.text()
    assert "偏低" in low, "低对比配色没有提示：%s" % low
    d._apply_preset(PRESETS[0])
    app.processEvents()
    return "高对比正常、低对比有提示"


check("打开设置面板", t_open)
check("改字号生效", t_change_font_size)
check("改行距生效", t_change_line_height)
check("预设主题", t_preset)
check("模式切换联动", t_mode_switch)
check("对比度提示", t_contrast)

print("\n== 2. 取色器采样 ==")


def make_shot(w_log=200, h_log=100, dpr=1):
    img = QImage(w_log * dpr, h_log * dpr, QImage.Format.Format_RGB32)
    img.fill(QColor("#102030"))
    # 在逻辑坐标 (60,25) 处画一个 8x8 的设备像素块，颜色 #FF8800
    x0, y0 = 60 * dpr, 25 * dpr
    for dy in range(8):
        for dx in range(8):
            img.setPixelColor(x0 + dx, y0 + dy, QColor("#FF8800"))
    # 左上角一个绿点
    img.setPixelColor(1, 1, QColor("#00FF00"))
    return [(QRect(0, 0, w_log, h_log), img)]


def t_sample_basic():
    d = Eyedropper(make_shot())
    d.show()
    app.processEvents()
    c, detail = d.sample_at(QPoint(62, 27))
    assert c is not None, "采样返回 None"
    assert c.name() == "#ff8800", "采样颜色不对：%s" % c.name()
    assert detail[1] == 62 and detail[2] == 27, "设备像素坐标不对：%r" % (detail[1:],)
    d.close()
    return "1:1 采样命中 #ff8800"


def t_sample_dpr():
    """DPR=2 时，逻辑坐标必须换算成设备像素，否则会偏一半。"""
    d = Eyedropper(make_shot(dpr=2))
    d.show()
    app.processEvents()
    c, detail = d.sample_at(QPoint(62, 27))
    assert c is not None
    assert c.name() == "#ff8800", "DPR=2 采样偏了：%s（设备坐标 %r）" % (c.name(), detail[1:])
    assert detail[1] == 124 and detail[2] == 54, "设备坐标应为 124,54，实际 %r" % (detail[1:],)
    d.close()
    return "DPR=2 正确换算到设备像素 124,54"


def t_sample_corner():
    d = Eyedropper(make_shot())
    d.show()
    app.processEvents()
    c, _ = d.sample_at(QPoint(1, 1))
    assert c is not None and c.name() == "#00ff00", "角点采样不对：%s" % (c and c.name())
    d.close()
    return "角点像素准确"


def t_sample_outside():
    d = Eyedropper(make_shot())
    d.show()
    app.processEvents()
    c, detail = d.sample_at(QPoint(-50, -50))
    assert c is None and detail is None, "越界应返回 None"
    d.close()
    return "越界返回 None"


def t_click_emits():
    d = Eyedropper(make_shot())
    got = {}
    d.picked.connect(lambda col: got.setdefault("color", col.name()))
    d.show()
    app.processEvents()
    pos = QPoint(62, 27)
    ev = QMouseEvent(QMouseEvent.Type.MouseButtonPress, pos,
                     d.mapToGlobal(pos), Qt.MouseButton.LeftButton,
                     Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
    d.mousePressEvent(ev)
    app.processEvents()
    assert got.get("color") == "#ff8800", "点击没有取到颜色：%r" % got
    return "左键点击发出 picked(#ff8800)"


check("1:1 采样", t_sample_basic)
check("DPR=2 缩放换算", t_sample_dpr)
check("角点采样", t_sample_corner)
check("越界保护", t_sample_outside)
check("点击发出颜色", t_click_emits)

print("\n== 3. 取色回填背景 ==")


def t_apply_color():
    win._on_color_picked(QColor("#123456"))
    app.processEvents()
    assert settings.get("appearance.bgColor") == "#123456", "背景色没写回"
    assert win._settings_dlg.btn_bg._color == "#123456", "设置面板色块没刷新"
    assert win.reader.pg.doc.toPlainText().strip(), "换背景后正文没了"
    win._settings_dlg._apply_preset(PRESETS[0])
    app.processEvents()
    return "取色结果回填背景并刷新面板"


check("取色回填背景", t_apply_color)

print("\n== 4. 主题辅助 ==")


def t_theme_helpers():
    assert is_dark("#000000") and not is_dark("#FFFFFF")
    assert mix("#000000", "#FFFFFF", 0.5).lower() == "#7f7f7f"
    return "is_dark / mix 正确"


check("主题计算函数", t_theme_helpers)

win.close_settings()
win._stop_worker()
win.hide()
library.close()

print("\n===== 结果: %d 通过 / %d 失败 =====" % (passed, failed))
sys.exit(0 if failed == 0 else 1)
