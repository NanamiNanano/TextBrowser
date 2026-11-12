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
        # 背景不透明度：只影响背景，文字始终不透明
        "bgOpacity": 1.0,
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
        # auto     = 托盘注册成功就收进托盘，失败则最小化到任务栏（默认）
        # tray     = 总是尝试收进托盘
        # minimize = 总是最小化到任务栏
        "escAction": "auto",
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
        self._migrate()

    # 配置结构版本。改过默认值且老默认值会被自动写进文件时，靠它做迁移——
    # 否则「改默认值」对已经存过配置的用户完全无效。
    SCHEMA = 3

    def _migrate(self) -> None:
        version = int(self.data.get("_schema", 1) or 1)
        if version < 2:
            # v1 时代 escAction 的默认值被写成 minimize（而且会被自动写盘），
            # 那不是用户的选择，恢复成 auto：托盘可用就收进托盘。
            window = self.data.setdefault("window", {})
            if window.get("escAction") == "minimize":
                window["escAction"] = "auto"
            self.data["_schema"] = 2
            version = 2
        if version < 3:
            # 旧版是「整窗半透明」（文字跟着变淡），改成「只有背景半透明」。
            # 老值 window.opacity 直接搬过来，视觉上不至于突变。
            old = self.data.get("window", {}).get("opacity")
            appearance = self.data.setdefault("appearance", {})
            try:
                if old is not None and float(old) < 0.999:
                    appearance["bgOpacity"] = max(0.0, min(1.0, float(old)))
            except (TypeError, ValueError):
                pass
            self.data["_schema"] = 3
            self.save()

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
