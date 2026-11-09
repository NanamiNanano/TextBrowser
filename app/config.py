# -*- coding: utf-8 -*-
"""全局路径与常量。"""
import os
import sys

APP_NAME = "TextBrowser"
APP_DISPLAY_NAME = "文本浏览器"
APP_VERSION = "0.1.0"

# 数据目录：优先 %APPDATA%\TextBrowser；若不可写则回落到程序目录旁的 data\
def _data_dir() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    cand = os.path.join(base, APP_NAME)
    try:
        os.makedirs(cand, exist_ok=True)
        probe = os.path.join(cand, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return cand
    except OSError:
        fallback = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
        os.makedirs(fallback, exist_ok=True)
        return fallback


DATA_DIR = _data_dir()
DB_PATH = os.path.join(DATA_DIR, "library.db")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
COVER_DIR = os.path.join(CACHE_DIR, "cover")

for _d in (CACHE_DIR, COVER_DIR):
    os.makedirs(_d, exist_ok=True)

SUPPORTED_EXTS = (".txt", ".epub")

# 打包/开发两种模式的资源根
RESOURCE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
