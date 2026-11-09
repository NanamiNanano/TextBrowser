# -*- coding: utf-8 -*-
"""自绘标题栏：拖动窗口、双击最大化、最小化/最大化/关闭按钮。

两个关键点：

1. **拖动走 `QWindow.startSystemMove()`**，不要自己算 offset —— 自己拖动会丢掉
   Windows 的贴边吸附（Aero Snap）。
2. **按钮图标用 QPainter 矢量绘制，绝不用 ✕ ▢ 这类生僻字符。** 实测用字符做
   图标会让 Qt/DirectWrite 为寻找字形去枚举整个字体库，首帧就多吃掉 474 MB
   内存；矢量绘制既没有这个问题，跨 DPI 也更清晰。
"""
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPalette, QPen
from PySide6.QtWidgets import (QAbstractButton, QHBoxLayout, QLabel, QWidget)


class WindowButton(QAbstractButton):
    """矢量绘制的窗口按钮：min / max / restore / close。"""

    HOVER_BG = None          # 由 apply_colors 设置

    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self._hover = False
        self._pressed = False
        self._fg = QColor("#2B2B2B")
        self._hover_bg = QColor(0, 0, 0, 20)
        self._close_hover_bg = QColor("#C94F4F")
        self.setFixedSize(36, 26)
        self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        tips = {"min": "最小化到托盘", "max": "最大化 / 还原",
                "restore": "最大化 / 还原", "close": "收起到托盘"}
        self.setToolTip(tips.get(kind, ""))

    def apply_colors(self, fg: str, hover_bg: str, close_hover: str = "#C94F4F"):
        self._fg = QColor(fg)
        self._hover_bg = QColor(hover_bg)
        self._close_hover_bg = QColor(close_hover)
        self.update()

    def set_kind(self, kind: str):
        if kind != self.kind:
            self.kind = kind
            self.update()

    def enterEvent(self, ev):
        self._hover = True
        self.update()
        super().enterEvent(ev)

    def leaveEvent(self, ev):
        self._hover = False
        self.update()
        super().leaveEvent(ev)

    def mousePressEvent(self, ev):
        self._pressed = True
        self.update()
        super().mousePressEvent(ev)

    def mouseReleaseEvent(self, ev):
        self._pressed = False
        self.update()
        super().mouseReleaseEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        r = QRectF(self.rect())

        if self._hover:
            bg = self._close_hover_bg if self.kind == "close" else self._hover_bg
            if self._pressed:
                bg = bg.darker(115)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 5, 5)

        # 关闭键悬停时图标转为白色
        color = QColor("#FFFFFF") if (self.kind == "close" and self._hover) else self._fg
        pen = QPen(color)
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)

        cx, cy = r.center().x(), r.center().y()
        w, h = 9.0, 9.0
        if self.kind == "min":
            p.drawLine(QPointF(cx - w / 2, cy + 0.5), QPointF(cx + w / 2, cy + 0.5))
        elif self.kind == "max":
            p.drawRect(QRectF(cx - w / 2, cy - h / 2, w, h))
        elif self.kind == "restore":
            p.drawRect(QRectF(cx - w / 2, cy - h / 2 + 2, w - 2, h - 2))
            p.drawLine(QPointF(cx - w / 2 + 2, cy - h / 2),
                       QPointF(cx + w / 2, cy - h / 2))
            p.drawLine(QPointF(cx + w / 2, cy - h / 2),
                       QPointF(cx + w / 2, cy + h / 2 - 2))
        elif self.kind == "close":
            d = w / 2
            p.drawLine(QPointF(cx - d, cy - d), QPointF(cx + d, cy + d))
            p.drawLine(QPointF(cx + d, cy - d), QPointF(cx - d, cy + d))
        p.end()


class TitleBar(QWidget):
    sig_minimize = Signal()
    sig_maximize = Signal()
    sig_close = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setFixedHeight(40)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 8, 6)
        lay.setSpacing(10)

        self.lbl_app = QLabel("文本浏览器")
        self.lbl_app.setObjectName("AppName")
        self.lbl_book = QLabel("")
        self.lbl_book.setObjectName("BookTitle")

        lay.addWidget(self.lbl_app)
        lay.addWidget(self.lbl_book)
        lay.addStretch(1)

        self.btn_min = WindowButton("min", self)
        self.btn_max = WindowButton("max", self)
        self.btn_close = WindowButton("close", self)
        for b in (self.btn_min, self.btn_max, self.btn_close):
            lay.addWidget(b)

        self.btn_min.clicked.connect(self.sig_minimize)
        self.btn_max.clicked.connect(self.sig_maximize)
        self.btn_close.clicked.connect(self.sig_close)

    # ------------------------------------------------------------ 主题
    def apply_colors(self, fg: str, muted: str, hover_bg: str):
        for b in (self.btn_min, self.btn_max, self.btn_close):
            b.apply_colors(muted, hover_bg)
        self.update()

    def set_title(self, text: str) -> None:
        self.lbl_book.setText(("·  " + text) if text else "")

    def set_maximized(self, maximized: bool) -> None:
        self.btn_max.set_kind("restore" if maximized else "max")

    # ------------------------------------------------------------ 交互
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            wh = win.windowHandle()
            if wh is not None:
                wh.startSystemMove()      # 交给系统，保留贴边吸附
                ev.accept()
                return
        super().mousePressEvent(ev)

    def mouseDoubleClickEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.sig_maximize.emit()
            ev.accept()
            return
        super().mouseDoubleClickEvent(ev)
