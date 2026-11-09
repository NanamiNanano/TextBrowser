# -*- coding: utf-8 -*-
"""把 wheel 解压安装到目标目录，不需要删除权限（pip 在受限环境会失败）。

用法: python install_wheel.py <目标目录> <wheel 文件...>

wheel 规范允许 <name>.data/{purelib,platlib,scripts,data,headers} 布局，
这里做最小实现：purelib/platlib 归入目标根，scripts 归入目标目录的 Scripts/。
"""
import os
import sys
import zipfile

target = sys.argv[1]
wheels = sys.argv[2:]
os.makedirs(target, exist_ok=True)


def extract_wheel(wheel_path, target):
    n = 0
    with zipfile.ZipFile(wheel_path) as z:
        names = z.namelist()
        # 找出 .data 目录
        data_dirs = sorted({p.split("/")[0] for p in names if p.split("/")[0].endswith(".data")})
        for member in z.infolist():
            name = member.filename
            if name.endswith("/"):
                continue
            parts = name.split("/")
            root = parts[0]
            if root in data_dirs:
                kind = parts[1] if len(parts) > 1 else ""
                rest = "/".join(parts[2:])
                if not rest:
                    continue
                if kind in ("purelib", "platlib"):
                    dest_rel = rest
                elif kind == "scripts":
                    dest_rel = os.path.join("Scripts", os.path.basename(rest))
                elif kind == "data":
                    dest_rel = os.path.join("data", rest)
                else:
                    dest_rel = os.path.join(kind, rest)
            else:
                dest_rel = name
            dest = os.path.join(target, dest_rel.replace("/", os.sep))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with z.open(member) as src, open(dest, "wb") as dst:
                while True:
                    chunk = src.read(1 << 20)
                    if not chunk:
                        break
                    dst.write(chunk)
            n += 1
    return n


total = 0
for w in wheels:
    k = extract_wheel(w, target)
    total += k
    print("解压 %-60s %5d 个文件" % (os.path.basename(w), k))
print("共 %d 个文件 -> %s" % (total, target))

# PySide6 需要把 Qt 的 bin 目录加入 DLL 搜索路径；这里只做静态校验
for marker in ("PySide6/__init__.py", "PySide6/QtCore.pyd", "shiboken6/__init__.py"):
    p = os.path.join(target, marker.replace("/", os.sep))
    print("%-28s %s" % (marker, "OK" if os.path.exists(p) else "MISSING"))
