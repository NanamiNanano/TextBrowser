# -*- coding: utf-8 -*-
"""全屏取色器（屏幕取色）。

流程上有两个不能颠倒的步骤：
  1. **先截图**：把每块屏幕当前画面抓成 QImage；
  2. **再显示遮罩**：全屏无边框置顶窗口，把抓到的图贴上去当“冻结的画面”。

如果先把遮罩显示出来再截图，遮罩本身就会被截进去，吸到的永远是黑色/半透明色。

坐标换算要考虑 DPI 与多屏：`QScreen.grabWindow(0)` 返回的是**设备像素**，
而 `QScreen.geometry()` 是**逻辑像素**，两者比例就是 devicePixelRatio。
"""
from PySide6.QtCore import QPoint, QRect, QRectF, Qt, Signal
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QPainter,
                           QPen, QPixmap)
from PySide6.QtWidgets import QWidget

LOUPE = 132            # 放大镜边长（像素）
GRID = 11              # 放大镜内显示多少×多少像素
DIM_ALPHA = 40         # 遮罩变暗程度，太低看不出准星，太高看不准颜色


class Eyedropper(QWidget):
    picked = Signal(QColor)
    cancelled = Signal()

    def __init__(self, shots=None, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setMouseTracking(True)

        if shots is None:
            shots = self.capture()
        # [(逻辑矩形 QRect, 设备像素 QImage)]
        self._shots = [(QRect(geo), pm if isinstance(pm, QImage) else pm.toImage())
                       for geo, pm in shots]

        rect = QRect()
        for geo, _ in self._shots:
            rect = geo if rect.isNull() else rect.united(geo)
        self._virtual = rect
        self.setGeometry(rect)

        self._pos = QPoint(rect.width() // 2, rect.height() // 2)
        self._color = QColor("#000000")

    # ------------------------------------------------------------ 截图
    @staticmethod
    def capture():
        """抓取所有屏幕。必须在窗口 show() 之前调用。"""
        shots = []
        for screen in QGuiApplication.screens():
            pm = screen.grabWindow(0)
            if pm.isNull():
                continue
            shots.append((screen.geometry(), pm))
        return shots

    # ------------------------------------------------------------ 采样
    def sample_at(self, widget_pos: QPoint):
        """返回 (QColor, (QImage, x, y))；越界返回 (None, None)。"""
        g = self.mapToGlobal(widget_pos)
        for geo, img in self._shots:
            if not geo.contains(g):
                continue
            local = g - geo.topLeft()
            # 逻辑坐标 -> 设备像素
            sx = img.width() / max(1, geo.width())
            sy = img.height() / max(1, geo.height())
            x = int(local.x() * sx)
            y = int(local.y() * sy)
            x = max(0, min(x, img.width() - 1))
            y = max(0, min(y, img.height() - 1))
            return img.pixelColor(x, y), (img, x, y)
        return None, None

    def current_color(self) -> QColor:
        color, _ = self.sample_at(self._pos)
        return color or QColor("#000000")

    # ------------------------------------------------------------ 绘制
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 1) 贴冻结画面
        for geo, img in self._shots:
            target = QRectF(geo.translated(-self._virtual.topLeft()))
            p.drawImage(target, img)

        # 2) 轻微压暗，让准星与放大镜更清楚
        p.fillRect(self.rect(), QColor(0, 0, 0, DIM_ALPHA))

        color, detail = self.sample_at(self._pos)
        if color is None or detail is None:
            return
        img, sx, sy = detail
        self._color = color

        # 3) 准星
        p.setPen(QPen(QColor(255, 255, 255, 200), 1))
        x, y = self._pos.x(), self._pos.y()
        p.drawLine(0, y, x - 12, y)
        p.drawLine(x + 12, y, self.width(), y)
        p.drawLine(x, 0, x, y - 12)
        p.drawLine(x, y + 12, x, self.height())

        # 4) 放大镜：以光标为中心，取 GRID×GRID 个设备像素放大
        half = GRID // 2
        src = QRect(sx - half, sy - half, GRID, GRID)
        box = QRect(x + 18, y + 18, LOUPE, LOUPE)
        if box.right() > self.width():
            box.moveLeft(x - 18 - LOUPE)
        if box.bottom() > self.height():
            box.moveTop(y - 18 - LOUPE)

        p.fillRect(box, QColor(20, 20, 20, 235))
        p.drawImage(box.adjusted(2, 2, -2, -2), img, src)

        # 网格
        p.setPen(QPen(QColor(255, 255, 255, 45), 1))
        cell = (LOUPE - 4) / GRID
        for i in range(1, GRID):
            gx = box.left() + 2 + i * cell
            gy = box.top() + 2 + i * cell
            p.drawLine(int(gx), box.top() + 2, int(gx), box.bottom() - 2)
            p.drawLine(box.left() + 2, int(gy), box.right() - 2, int(gy))

        # 中心格高亮
        p.setPen(QPen(QColor(255, 255, 255, 230), 2))
        p.drawRect(QRectF(box.left() + 2 + half * cell, box.top() + 2 + half * cell,
                          cell, cell))
        p.setPen(QPen(QColor(255, 255, 255, 160), 1))
        p.drawRect(box)

        # 5) 色值文字
        hex_text = color.name().upper()
        rgb_text = "RGB(%d, %d, %d)" % (color.red(), color.green(), color.blue())
        f = QFont("Microsoft YaHei")
        f.setPixelSize(12)
        p.setFont(f)

        label = QRect(box.left(), box.bottom() + 8, max(LOUPE, 120), 40)
        p.fillRect(label.adjusted(-2, -2, 2, 2), QColor(20, 20, 20, 225))
        p.setPen(QColor(255, 255, 255, 240))
        p.drawText(label, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                   hex_text)
        p.setPen(QColor(200, 200, 200, 220))
        p.drawText(label, int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom),
                   rgb_text)

        # 6) 操作提示
        hint = "左键取色    ESC 取消"
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRect(0, self.height() - 40, self.width(), 30),
                   int(Qt.AlignmentFlag.AlignCenter), hint)

    # ------------------------------------------------------------ 事件
    def mouseMoveEvent(self, ev):
        self._pos = ev.position().toPoint()
        self.update()

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            color, _ = self.sample_at(ev.position().toPoint())
            if color is not None:
                self.picked.emit(color)
            self.close()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            self.close()
            return
        super().keyPressEvent(ev)


def pick_color(parent=None):
    """便捷入口：阻塞式取色，返回 QColor 或 None。

    仅供脚本/测试使用；界面里请用 MainWindow 的非阻塞方式，
    否则遮罩的鼠标事件会被模态循环吞掉。
    """
    from PySide6.QtCore import QEventLoop

    shots = Eyedropper.capture()
    if not shots:
        return None
    dlg = Eyedropper(shots, parent)
    result = {"color": None}
    loop = QEventLoop()

    def _done(color):
        result["color"] = color
        loop.quit()

    dlg.picked.connect(_done)
    dlg.cancelled.connect(loop.quit)
    dlg.show()
    loop.exec()
    dlg.close()
    return result["color"]
