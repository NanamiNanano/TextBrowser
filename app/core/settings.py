# -*- coding: utf-8 -*-
"""外观与阅读设置的持久化（JSON）。"""
import copy
import json
import os
from typing import Any, Dict

from ..config import SETTINGS_PATH

DEFAULTS: Dict[str, Any] = {
    "appearance": {
        "bgColor": "#F5EFE0",
        "textColor": "#2B2B2B",
        "fontFamily": "Microsoft YaHei",
        "fontSize": 20,
        "lineHeight": 1.8,
        "letterSpacing": 0.0,
        "paragraphSpacing": 8,
        "textIndent": 0,
        "align": "left",             # left | justify（中文两端对齐易出字间隙，默认左对齐）
        "marginH": 48,
        "marginV": 36,
        "maxContentWidth": 780,
    },
    "reading": {
        "mode": "paginate",
        "showFooter": True,
        "clickZone": False,
    },
    "window": {
        "frameless": True,
        "pureMode": False,
        "opacity": 1.0,
        "x": 220,
        "y": 130,
        "w": 1120,
        "h": 780,
        "maximized": False,
        # minimize = 最小化到任务栏（任务栏留有图标，一定找得回来）
        # tray     = 收进系统托盘（更"干净"，但依赖托盘图标注册成功）
        "escAction": "minimize",
    },
    "shortcuts": {
        "prevPage": "Q",
        "nextPage": "E",
        "tray": "Escape",
    },
    "perBookAppearance": False,
}

# 预设配色（PRD FR-6.6）
PRESETS = [
    {"name": "羊皮纸", "bg": "#F5EFE0", "fg": "#2B2B2B"},
    {"name": "日间白", "bg": "#FFFFFF", "fg": "#1F2328"},
    {"name": "护眼绿", "bg": "#CCE8CF", "fg": "#2A3A2C"},
    {"name": "深灰", "bg": "#2B2B2B", "fg": "#C8C8C8"},
    {"name": "纯黑", "bg": "#000000", "fg": "#9A9A9A"},
]


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """点号访问的配置对象：settings.get('appearance.fontSize')。"""

    def __init__(self, path: str = SETTINGS_PATH):
        self.path = path
        self.data = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                self.data = _deep_merge(DEFAULTS, json.load(f))
        except (OSError, ValueError):
            self.data = copy.deepcopy(DEFAULTS)

    def save(self) -> bool:
        tmp = self.path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
            return True
        except OSError:
            return False

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value

    def reset(self) -> None:
        self.data = copy.deepcopy(DEFAULTS)
        self.save()
