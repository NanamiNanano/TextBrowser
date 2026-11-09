# -*- coding: utf-8 -*-
"""主题：动态生成 QSS、封面与图标。"""
import hashlib

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (QBrush, QColor, QFont, QIcon, QLinearGradient,
                           QPainter, QPainterPath, QPen, QPixmap)

from ..core.settings import Settings

COVER_GRADIENTS = [
    ("#7C8FA6", "#4E6076"), ("#A6887C", "#7A5E51"), ("#8AA67C", "#5E7A51"),
    ("#A67CA6", "#7A5177"), ("#7CA6A0", "#51777A"), ("#A6A07C", "#7A7551"),
]


def _luminance(hex_color: str) -> float:
    c = QColor(hex_color)
    return (0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue()) / 255.0


def is_dark(bg: str) -> bool:
    return _luminance(bg) < 0.5


def mix(a: str, b: str, t: float) -> str:
    ca, cb = QColor(a), QColor(b)
    return QColor(
        int(ca.red() + (cb.red() - ca.red()) * t),
        int(ca.green() + (cb.green() - ca.green()) * t),
        int(ca.blue() + (cb.blue() - ca.blue()) * t),
    ).name()


def ui_colors(s: Settings) -> dict:
    """集中算一次配色，QSS 与自绘控件共用同一份，避免两边色值不一致。"""
    bg = s.get("appearance.bgColor", "#F5EFE0")
    fg = s.get("appearance.textColor", "#2B2B2B")
    dark = is_dark(bg)
    return {
        "bg": bg,
        "fg": fg,
        "dark": dark,
        "panel": mix(bg, "#000000" if dark else "#FFFFFF", 0.10 if dark else 0.55),
        "hover": mix(bg, fg, 0.10),
        "press": mix(bg, fg, 0.18),
        "border": mix(bg, fg, 0.22),
        "muted": mix(fg, bg, 0.45),
        "accent": "#4A7BD6" if not dark else "#6E9BEA",
    }


def build_qss(s: Settings) -> str:
    c = ui_colors(s)
    bg, fg, dark = c["bg"], c["fg"], c["dark"]
    panel, hover, press = c["panel"], c["hover"], c["press"]
    border, muted, accent = c["border"], c["muted"], c["accent"]

    return f"""
    QWidget {{
        color: {fg};
        font-family: "Microsoft YaHei";
    }}
    QWidget#Root {{
        background: {bg};
    }}
    QWidget#TitleBar {{
        background: transparent;
    }}
    QLabel#AppName {{
        font-size: 13px;
        font-weight: 600;
        letter-spacing: 1px;
    }}
    QLabel#BookTitle {{
        font-size: 13px;
        color: {muted};
    }}
    QToolButton#WinBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        width: 34px;
        height: 26px;
        font-size: 13px;
        color: {muted};
    }}
    QToolButton#WinBtn:hover {{
        background: {hover};
        color: {fg};
    }}
    QToolButton#WinBtn:pressed {{
        background: {press};
    }}
    QToolButton#CloseBtn {{
        background: transparent;
        border: none;
        border-radius: 6px;
        width: 34px;
        height: 26px;
        font-size: 13px;
        color: {muted};
    }}
    QToolButton#CloseBtn:hover {{
        background: #C94F4F;
        color: #FFFFFF;
    }}
    QPushButton {{
        background: {panel};
        border: 1px solid {border};
        border-radius: 8px;
        padding: 7px 16px;
        font-size: 13px;
    }}
    QPushButton:hover {{
        background: {hover};
        border-color: {accent};
    }}
    QPushButton:pressed {{
        background: {press};
    }}
    QPushButton#Primary {{
        background: {accent};
        color: #FFFFFF;
        border: none;
        font-weight: 600;
    }}
    QPushButton#Primary:hover {{
        background: {mix(accent, '#FFFFFF', 0.15)};
    }}
    QScrollArea {{
        background: transparent;
        border: none;
    }}
    QScrollArea > QWidget > QWidget {{
        background: transparent;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {mix(bg, fg, 0.25)};
        border-radius: 5px;
        min-height: 30px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {mix(bg, fg, 0.40)};
    }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
        height: 0px;
    }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
        background: transparent;
    }}
    QProgressBar {{
        background: {mix(bg, fg, 0.10)};
        border: none;
        border-radius: 2px;
        height: 4px;
        text-align: center;
    }}
    QProgressBar::chunk {{
        background: {accent};
        border-radius: 2px;
    }}
    QLabel#SectionTitle {{
        font-size: 17px;
        font-weight: 600;
    }}
    QLabel#Muted {{
        color: {muted};
        font-size: 12px;
    }}
    QLabel#BookCardTitle {{
        font-size: 15px;
        font-weight: 600;
    }}
    QWidget#TocPanel {{
        background: {panel};
        border-left: 1px solid {border};
    }}
    QWidget#TocHeader {{
        background: transparent;
    }}
    QLabel#TocTitle {{
        font-size: 13px;
        font-weight: 600;
    }}
    QPushButton#TocClose {{
        background: transparent;
        border: none;
        border-radius: 11px;
        padding: 0px;
        font-size: 15px;
        color: {muted};
    }}
    QPushButton#TocClose:hover {{
        background: {hover};
        color: {fg};
    }}
    QListWidget#TocList {{
        background: transparent;
        border: none;
        outline: none;
        padding: 2px 6px 6px 6px;
    }}
    QListWidget#TocList::item {{
        padding: 6px 8px;
        border-radius: 6px;
        color: {fg};
    }}
    QListWidget#TocList::item:hover {{
        background: {hover};
    }}
    QListWidget#TocList::item:selected {{
        background: {accent};
        color: #FFFFFF;
    }}
    QToolTip {{
        background: {panel};
        color: {fg};
        border: 1px solid {border};
        padding: 4px 8px;
    }}
    """


def cover_pixmap(title: str, w: int = 56, h: int = 76) -> QPixmap:
    """按书名生成稳定配色的封面（TXT 没有封面图）。"""
    idx = int(hashlib.md5(title.encode("utf-8")).hexdigest(), 16) % len(COVER_GRADIENTS)
    c1, c2 = COVER_GRADIENTS[idx]

    pm = QPixmap(w, h)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)

    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), 5, 5)
    grad = QLinearGradient(0, 0, w, h)
    grad.setColorAt(0.0, QColor(c1))
    grad.setColorAt(1.0, QColor(c2))
    p.fillPath(path, QBrush(grad))

    # 书脊
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(255, 255, 255, 28))
    p.drawRect(QRectF(0, 0, 5, h))

    f = QFont("Microsoft YaHei")
    f.setPixelSize(int(h * 0.30))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor(255, 255, 255, 235))
    ch = title.strip()[:1] or "书"
    p.drawText(QRectF(5, 0, w - 5, h), Qt.AlignmentFlag.AlignCenter, ch)
    p.end()
    return pm


def app_icon(size: int = 64) -> QIcon:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(2, 2, size - 4, size - 4), size * 0.22, size * 0.22)
    grad = QLinearGradient(0, 0, size, size)
    grad.setColorAt(0.0, QColor("#5B8DEF"))
    grad.setColorAt(1.0, QColor("#3A62B8"))
    p.fillPath(path, QBrush(grad))
    f = QFont("Microsoft YaHei")
    f.setPixelSize(int(size * 0.52))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("#FFFFFF"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "文")
    p.end()
    return QIcon(pm)


def tray_icon() -> QIcon:
    """托盘图标：多尺寸，深浅色任务栏都能看清。"""
    icon = QIcon()
    for s in (16, 24, 32, 48, 64):
        pm = QPixmap(s, s)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(QRectF(1, 1, s - 2, s - 2), s * 0.20, s * 0.20)
        grad = QLinearGradient(0, 0, s, s)
        grad.setColorAt(0.0, QColor("#5B8DEF"))
        grad.setColorAt(1.0, QColor("#3A62B8"))
        p.fillPath(path, QBrush(grad))
        f = QFont("Microsoft YaHei")
        f.setPixelSize(max(7, int(s * 0.60)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QPen(QColor("#FFFFFF")))
        p.drawText(QRectF(0, 0, s, s), Qt.AlignmentFlag.AlignCenter, "文")
        p.end()
        icon.addPixmap(pm)
    return icon
