# -*- coding: utf-8 -*-
"""窗口内提示条。

用于那些「需要告诉用户但不该打断他」的情况（例如托盘不可用、自动降级到最小化）。
刻意不用 QMessageBox：模态框会把阅读打断，还得手动点掉。
"""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton

NOTICE_HEIGHT = 34


class NoticeBar(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("NoticeBar")
        self.setFixedHeight(NOTICE_HEIGHT)

        # 定时器必须先建好：setVisible(False) 会触发 hideEvent
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 8, 0)
        lay.setSpacing(8)

        self.lbl = QLabel("")
        self.lbl.setObjectName("NoticeText")
        self.lbl.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        lay.addWidget(self.lbl, 1)

        self.btn_close = QPushButton("×")
        self.btn_close.setObjectName("NoticeClose")
        self.btn_close.setFixedSize(20, 20)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setToolTip("关闭提示")
        self.btn_close.clicked.connect(self.hide)
        lay.addWidget(self.btn_close)
        self.setVisible(False)

    def show_message(self, text: str, msec: int = 9000) -> None:
        self.lbl.setText(text)
        self.setVisible(True)
        if msec > 0:
            self._timer.start(msec)
        else:
            self._timer.stop()

    def hide(self) -> None:                # noqa: A003 - 覆盖 QWidget.hide 是有意的
        self._timer.stop()
        super().hide()

    def hideEvent(self, ev):
        self._timer.stop()
        super().hideEvent(ev)
