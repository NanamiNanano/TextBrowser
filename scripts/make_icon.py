# -*- coding: utf-8 -*-
"""生成 assets/app.ico —— 快捷方式与任务栏用的图标。

用 Qt 按同一份绘制逻辑渲染 256px 底图，再交给 Pillow 打多尺寸 ico，
保证快捷方式图标和程序内图标是同一个图形（不会出现两种风格）。
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "vendor", "py312"))
sys.path.insert(0, ROOT)

from PySide6.QtWidgets import QApplication  # noqa: E402

from app.ui.theme import app_icon  # noqa: E402

OUT_DIR = os.path.join(ROOT, "assets")
os.makedirs(OUT_DIR, exist_ok=True)

app = QApplication([])
png_tmp = os.path.join(OUT_DIR, "_icon_256.png")
ico_path = os.path.join(OUT_DIR, "app.ico")

pm = app_icon(256).pixmap(256, 256)
pm.save(png_tmp, "PNG")
print("渲染 256px: %dx%d" % (pm.width(), pm.height()))

from PIL import Image  # noqa: E402

img = Image.open(png_tmp).convert("RGBA")
sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(ico_path, format="ICO", sizes=sizes)
print("写出 %s  %.1f KB" % (ico_path, os.path.getsize(ico_path) / 1024))

# 顺带留一份 png，方便别处引用
img.save(os.path.join(OUT_DIR, "app_256.png"))
try:
    os.remove(png_tmp)
except OSError:
    pass

from PIL import IcoImagePlugin  # noqa: E402,F401

with Image.open(ico_path) as check:
    print("校验: ico 内尺寸 =", sorted(check.info.get("sizes", [])))
