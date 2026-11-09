# -*- coding: utf-8 -*-
"""主窗口：无边框外壳 + 视图切换 + 快捷键仲裁。

无边框要点：
  * 标题栏拖动走 QWindow.startSystemMove()，保留系统贴边吸附；
  * 四边四角放透明「抓取条」，按下时走 startSystemResize()，由系统负责缩放；
  * 最大化时隐藏抓取条，避免和系统边框打架。
"""
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from ..config import APP_DISPLAY_NAME
from ..core.paginate import Page
from ..core.settings import Settings
from .bookshelf import BookshelfView
from .reader import ReaderView
from .search_panel import SearchPanel
from .theme import build_qss, ui_colors
from .titlebar import TitleBar
from .toc_panel import TocPanel
from .tray import Tray

GRIP = 6
CORNER = 14


class ResizeGrip(QWidget):
    """透明抓取条：按下即交给系统做窗口缩放。"""

    def __init__(self, parent, edges, cursor):
        super().__init__(parent)
        self.edges = edges
        self.setCursor(cursor)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setStyleSheet("background: transparent;")

    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            wh = win.windowHandle()
            if wh is not None:
                wh.startSystemResize(self.edges)
                ev.accept()
                return
        super().mousePressEvent(ev)


class MainWindow(QWidget):
    def __init__(self, settings: Settings, library, enable_tray: bool = True):
        super().__init__()
        self.settings = settings
        self.library = library
        self._tray_hint_shown = False
        self.enable_tray = enable_tray

        self.setObjectName("Root")
        self.setWindowTitle(APP_DISPLAY_NAME)
        self.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint)
        self.setMinimumSize(720, 520)
        self.setMouseTracking(True)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(self)
        root.addWidget(self.titlebar)

        self.stack = QStackedWidget(self)
        self.shelf = BookshelfView(library, self)
        self.reader = ReaderView(settings, library, self)
        self.stack.addWidget(self.shelf)
        self.stack.addWidget(self.reader)

        # 正文区 + 右侧栏（目录 / 搜索共用，默认收起）
        self.toc = TocPanel(self)
        self.search = SearchPanel(self)
        self.side = QStackedWidget(self)
        self.side.addWidget(self.toc)
        self.side.addWidget(self.search)
        self.side.setVisible(False)
        content = QWidget(self)
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)
        content_lay.addWidget(self.stack, 1)
        content_lay.addWidget(self.side)
        root.addWidget(content, 1)

        # 托盘
        self.tray = Tray(lambda: self.library.list_books(), self)
        self.tray.sig_show.connect(self.show_from_tray)
        self.tray.sig_quit.connect(self.quit_app)
        if enable_tray:
            self.tray.show()

        # 信号
        self.titlebar.sig_minimize.connect(self.hide_to_tray)
        self.titlebar.sig_maximize.connect(self.toggle_maximize)
        self.titlebar.sig_close.connect(self.hide_to_tray)
        self.shelf.sig_open_book.connect(self.open_book)
        self.shelf.sig_status.connect(self.show_status)
        self.reader.sig_status.connect(self.show_status)
        self.reader.sig_progress.connect(self._on_progress)
        self.toc.sig_jump.connect(self._on_toc_jump)
        self.toc.sig_close.connect(self.close_side)
        self.search.sig_jump.connect(self._on_search_jump)
        self.search.sig_close.connect(self.close_side)

        # 缩放抓取条
        self._grips = []
        self._build_grips()

        self._restore_geometry()
        self.apply_theme()

    # ------------------------------------------------------------ 主题
    def apply_theme(self):
        """QSS 与自绘标题栏用同一份配色，改主题时两边一起刷新。"""
        c = ui_colors(self.settings)
        self.setStyleSheet(build_qss(self.settings))
        self.titlebar.apply_colors(c["muted"], c["muted"], c["hover"])

    # ------------------------------------------------------------ 抓取条
    def _build_grips(self):
        c = Qt.CursorShape
        spec = [
            ("top", c.SizeVerCursor), ("bottom", c.SizeVerCursor),
            ("left", c.SizeHorCursor), ("right", c.SizeHorCursor),
            ("topleft", c.SizeFDiagCursor), ("topright", c.SizeBDiagCursor),
            ("bottomleft", c.SizeBDiagCursor), ("bottomright", c.SizeFDiagCursor),
        ]
        for name, cur in spec:
            g = ResizeGrip(self, self._edges_for(name), cur)
            self._grips.append((name, g))

    @staticmethod
    def _edges_for(name):
        e = Qt.Edge
        table = {
            "top": e.TopEdge, "bottom": e.BottomEdge,
            "left": e.LeftEdge, "right": e.RightEdge,
            "topleft": e.TopEdge | e.LeftEdge,
            "topright": e.TopEdge | e.RightEdge,
            "bottomleft": e.BottomEdge | e.LeftEdge,
            "bottomright": e.BottomEdge | e.RightEdge,
        }
        return table[name]

    def _place_grips(self):
        w, h = self.width(), self.height()
        geo = {
            "top": (CORNER, 0, w - CORNER * 2, GRIP),
            "bottom": (CORNER, h - GRIP, w - CORNER * 2, GRIP),
            "left": (0, CORNER, GRIP, h - CORNER * 2),
            "right": (w - GRIP, CORNER, GRIP, h - CORNER * 2),
            "topleft": (0, 0, CORNER, CORNER),
            "topright": (w - CORNER, 0, CORNER, CORNER),
            "bottomleft": (0, h - CORNER, CORNER, CORNER),
            "bottomright": (w - CORNER, h - CORNER, CORNER, CORNER),
        }
        maxed = self.isMaximized()
        for name, g in self._grips:
            x, y, gw, gh = geo[name]
            g.setGeometry(int(x), int(y), int(max(0, gw)), int(max(0, gh)))
            g.setVisible(not maxed)
            g.raise_()

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._place_grips()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._place_grips()

    # ------------------------------------------------------------ 窗口
    def _restore_geometry(self):
        w = self.settings.get("window.w", 1120)
        h = self.settings.get("window.h", 780)
        x = self.settings.get("window.x", 220)
        y = self.settings.get("window.y", 130)
        self.resize(int(w), int(h))
        # 越界校正：换显示器/改分辨率后不要跑到屏幕外
        screens = QGuiApplication.screens()
        rect = None
        for s in screens:
            r = s.availableGeometry()
            if r.contains(x + 80, y + 40):
                rect = r
                break
        if rect is None and screens:
            rect = screens[0].availableGeometry()
            x = rect.x() + max(0, (rect.width() - int(w)) // 2)
            y = rect.y() + max(0, (rect.height() - int(h)) // 3)
        self.move(int(x), int(y))
        self.apply_opacity()
        if self.settings.get("window.maximized", False):
            self.showMaximized()

    def _save_geometry(self):
        if not self.isMaximized():
            g = self.geometry()
            self.settings.set("window.x", g.x())
            self.settings.set("window.y", g.y())
            self.settings.set("window.w", g.width())
            self.settings.set("window.h", g.height())
        self.settings.set("window.maximized", self.isMaximized())
        self.settings.save()

    def apply_opacity(self):
        try:
            self.setWindowOpacity(float(self.settings.get("window.opacity", 1.0)))
        except (TypeError, ValueError):
            pass

    def toggle_maximize(self):
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.titlebar.set_maximized(self.isMaximized())
        self._place_grips()

    # ------------------------------------------------------------ 托盘
    def hide_to_tray(self):
        self._save_geometry()
        if self.tray.isVisible() and self.tray.isSystemTrayAvailable():
            self.hide()
            if not self._tray_hint_shown:
                self._tray_hint_shown = True
                self.tray.notify("已最小化到托盘。双击托盘图标可恢复，托盘菜单里可退出。")
        else:
            self.showMinimized()      # 没有托盘就退化成普通最小化

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.reader.setFocus()

    def quit_app(self):
        self.reader.close_book()
        self._save_geometry()
        self.tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    # ------------------------------------------------------------ 文档
    def open_book(self, book_id: int):
        book = self.library.get_book(book_id)
        if not book:
            self.show_status("找不到这本书的记录")
            return
        if not book.get("exists", True):
            self.show_status("源文件已不存在：%s" % book["file_path"])
            return
        if self.reader.open_book(book):
            self.stack.setCurrentWidget(self.reader)
            self.titlebar.set_title(book["title"])
            self.toc.clear()
            self.search.set_target(None, [])
            self.reader.clear_search_hits()
            # 目录延后到首帧之后加载：100 MB TXT 首次识别约 170 ms，
            # 不该挡在第一页显示之前；二次打开走缓存，几乎无感。
            QTimer.singleShot(40, self._load_toc)
        else:
            self.shelf.refresh()

    # ------------------------------------------------------------ 侧栏
    def _side_showing(self, panel) -> bool:
        return self.side.isVisible() and self.side.currentWidget() is panel

    def open_side(self, panel) -> None:
        self.side.setCurrentWidget(panel)
        self.side.setVisible(True)

    def close_side(self) -> None:
        self.side.setVisible(False)
        self.reader.setFocus()

    def toggle_toc(self):
        if self._side_showing(self.toc):
            self.close_side()
            return
        self._load_toc()
        self.open_side(self.toc)
        self.toc.highlight_offset(self.reader.page.start)
        self.reader.setFocus()

    def toggle_search(self):
        if self._side_showing(self.search):
            self.close_side()
            return
        self._load_toc()                 # 结果里要显示章节名，需要章节表
        self.open_side(self.search)
        self.search.focus_input()

    def _load_toc(self):
        """载入（必要时现场识别）当前书的章节，同步给阅读视图、目录与搜索。"""
        book = self.reader.book
        if not book:
            self.toc.clear()
            self.search.set_target(None, [])
            return
        chapters = self.library.ensure_chapters(book)
        self.reader.set_chapters(chapters)
        self.toc.set_chapters(chapters)
        self.toc.highlight_offset(self.reader.page.start)
        self.search.set_target(self.reader.tf, chapters)
        if not chapters and self.side.currentWidget() is self.toc and self.side.isVisible():
            self.show_status("未识别到章节，可能是文件命名没有规律")

    def _on_toc_jump(self, offset: int):
        if self.reader.tf is None:
            return
        self.reader.goto_offset(offset)
        self.reader.setFocus()

    def _on_search_jump(self, offset: int, length: int):
        if self.reader.tf is None:
            return
        hits = [(h.offset, h.length) for h in self.search.current_hits()]
        self.reader.set_search_hits(hits, current=(offset, length))
        self.reader.goto_offset(offset, align_line=True)
        self.reader.setFocus()

    def back_to_shelf(self):
        self.reader.close_book()
        self.stack.setCurrentWidget(self.shelf)
        self.titlebar.set_title("")
        self.toc.clear()
        self.search.set_target(None, [])
        self.close_side()
        self.shelf.refresh()

    def show_status(self, text: str):
        # Qt 会自动把 applicationDisplayName 追加到标题后面，所以这里不要再拼
        # 应用名，否则会变成「xx —— yy - 文本浏览器」这种重复。
        self.setWindowTitle(text or APP_DISPLAY_NAME)

    def _on_progress(self, offset: int, pct: float):
        if self._side_showing(self.toc):
            self.toc.highlight_offset(offset)

    # ------------------------------------------------------------ 快捷键
    _INPUT_TYPES = (QLineEdit, QTextEdit)

    def _focus_in_input(self) -> bool:
        from PySide6.QtWidgets import QApplication
        w = QApplication.focusWidget()
        return isinstance(w, self._INPUT_TYPES)

    def keyPressEvent(self, ev):
        # 输入框聚焦时，所有单键快捷键（含 ESC/Q/E）让位给输入
        if self._focus_in_input():
            super().keyPressEvent(ev)
            return

        k = ev.key()
        ctrl = bool(ev.modifiers() & Qt.KeyboardModifier.ControlModifier)
        shift = bool(ev.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        in_reader = self.stack.currentWidget() is self.reader

        if ctrl and k == Qt.Key.Key_O:
            self.stack.setCurrentWidget(self.shelf)
            self.shelf.pick_files()
            ev.accept()
            return
        if ctrl and k == Qt.Key.Key_W:
            self.back_to_shelf()
            ev.accept()
            return
        if ctrl and k == Qt.Key.Key_T:
            if in_reader:
                self.toggle_toc()
            ev.accept()
            return
        if ctrl and k == Qt.Key.Key_F:
            if in_reader:
                self.toggle_search()
            ev.accept()
            return

        if k == Qt.Key.Key_Escape:
            self.hide_to_tray()
            ev.accept()
            return

        if k == Qt.Key.Key_Q or k == Qt.Key.Key_Left or k == Qt.Key.Key_PageUp:
            if in_reader:
                self.reader.prev_page()
            ev.accept()
            return

        if k == Qt.Key.Key_E or k == Qt.Key.Key_Right or k == Qt.Key.Key_PageDown:
            if in_reader:
                self.reader.next_page()
            ev.accept()
            return

        if k == Qt.Key.Key_Space:
            if in_reader:
                (self.reader.prev_page if shift else self.reader.next_page)()
            ev.accept()
            return

        if k == Qt.Key.Key_F11:
            self.toggle_maximize()
            ev.accept()
            return

        if in_reader and k in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self._bump_font(+1)
            ev.accept()
            return
        if in_reader and k == Qt.Key.Key_Minus:
            self._bump_font(-1)
            ev.accept()
            return

        super().keyPressEvent(ev)

    def _bump_font(self, delta: int):
        cur = int(self.settings.get("appearance.fontSize", 20))
        new = max(12, min(72, cur + delta))
        if new == cur:
            return
        self.settings.set("appearance.fontSize", new)
        self.settings.save()
        self.reader.apply_appearance()
        self.show_status("字号 %d px" % new)

    def closeEvent(self, ev):
        # 关闭按钮默认收起到托盘，真正退出走托盘菜单
        ev.ignore()
        self.hide_to_tray()
