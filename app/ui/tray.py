# -*- coding: utf-8 -*-
"""系统托盘。"""
from PySide6.QtCore import Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .theme import tray_icon


class Tray(QSystemTrayIcon):
    sig_show = Signal()
    sig_settings = Signal()
    sig_quit = Signal()

    def __init__(self, recent_provider=None, parent=None):
        super().__init__(tray_icon(), parent)
        self.setToolTip("文本浏览器 —— 双击显示窗口")
        self._recent_provider = recent_provider

        menu = QMenu()
        act_show = QAction("显示主窗口", menu)
        act_show.triggered.connect(self.sig_show)
        menu.addAction(act_show)

        self.menu_recent = menu.addMenu("最近阅读")
        self.menu_recent.aboutToShow.connect(self._fill_recent)

        menu.addSeparator()
        act_settings = QAction("偏好设置…", menu)
        act_settings.triggered.connect(self.sig_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.sig_quit)
        menu.addAction(act_quit)

        self.setContextMenu(menu)
        self.activated.connect(self._on_activated)

    def _on_activated(self, reason):
        if reason in (QSystemTrayIcon.ActivationReason.DoubleClick,
                      QSystemTrayIcon.ActivationReason.Trigger):
            self.sig_show.emit()

    def _fill_recent(self):
        self.menu_recent.clear()
        books = self._recent_provider() if self._recent_provider else []
        if not books:
            act = QAction("（暂无记录）", self.menu_recent)
            act.setEnabled(False)
            self.menu_recent.addAction(act)
            return
        for b in books[:5]:
            act = QAction("%s  —  %.1f%%" % (b["title"], b.get("percent") or 0.0),
                          self.menu_recent)
            act.setData(int(b["id"]))
            act.triggered.connect(lambda _=False, bid=int(b["id"]): self.sig_show.emit() or None)
            self.menu_recent.addAction(act)

    def notify(self, text: str, title: str = "文本浏览器") -> None:
        if self.supportsMessages():
            self.showMessage(title, text, self.icon(), 3000)
