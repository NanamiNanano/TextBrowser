#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双击入口 / 启动器。

设计要点：

1. **不依赖 PYTHONPATH**：自己把 vendor/py312 和项目根加进 sys.path，
   这样快捷方式里只写「pythonw.exe launcher.py」就能跑。
2. **pythonw 下没有控制台**：未捕获的异常会让用户只看到「双击了但什么都没发生」。
   所以这里必须把错误写成日志并弹窗，否则问题不可诊断。
3. **stdout/stderr 可能为 None**：pythonw 下 Qt 的警告会因为写不出去而抛异常，
   这里统一重定向到日志文件。
"""

import os
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
VENDOR = os.path.join(ROOT, "vendor", "py312")
LOG_DIR = os.path.join(ROOT, "build")
LOG_PATH = os.path.join(LOG_DIR, "launcher.log")


def _ensure_streams() -> None:
    """pythonw 下 sys.stdout/stderr 为 None，替换成日志文件，避免写日志时崩。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        return
    for name in ("stdout", "stderr"):
        if getattr(sys, name, None) is None:
            try:
                setattr(sys, name, open(LOG_PATH, "a", encoding="utf-8", buffering=1))
            except OSError:
                pass


def _report(module_error: str) -> None:
    """把失败原因写日志 + 弹窗。日志优先，弹窗兜底。"""
    try:
        os.makedirs(LOG_DIR, exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write("\n===== 启动失败 =====\n")
            f.write(module_error)
            f.write("\n")
    except OSError:
        pass

    msg = (
        "程序启动失败，详细信息已写入：\n%s\n\n%s"
        % (LOG_PATH, module_error.strip().splitlines()[-1][:300])
    )
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, msg, "文本浏览器 启动失败", 0x10)
    except Exception:
        pass


def main() -> int:
    _ensure_streams()

    if not os.path.isdir(VENDOR):
        _report("找不到依赖目录：%s\n请确认没有移动 vendor 文件夹。" % VENDOR)
        return 1

    # vendor 放前面：优先用随项目分发的 PySide6，不受系统已装版本干扰
    sys.path.insert(0, VENDOR)
    sys.path.insert(0, ROOT)

    from app.main import main as app_main
    return app_main()


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit:
        raise
    except BaseException:
        _report(traceback.format_exc())
        sys.exit(1)
