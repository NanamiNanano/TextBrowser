# -*- coding: utf-8 -*-
"""主窗口：无边框外壳 + 视图切换 + 快捷键仲裁。

无边框要点：
  * 标题栏拖动走 QWindow.startSystemMove()，保留系统贴边吸附；
  * 四边四角放透明「抓取条」，按下时走 startSystemResize()，由系统负责缩放；
  * 最大化时隐藏抓取条，避免和系统边框打架。
"""
import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (QHBoxLayout, QLineEdit, QStackedWidget,
                               QTextEdit, QVBoxLayout, QWidget)

from ..config import APP_DISPLAY_NAME
from ..core.paginate import Page
from ..core.settings import Settings
from .bookshelf import BookshelfView
from .bookmark_panel import BookmarkPanel
from .tray_win32 import Win32Tray
from .reader import ReaderView
from .search_panel import SearchPanel
from .theme import build_qss, ui_colors
from .titlebar import TitleBar
from .toc_panel import TocPanel
from .toc_worker import ChapterWorker

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
        self._chapter_worker = None
        self._settings_dlg = None
        self._dropper = None

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

        # 正文区 + 右侧栏（目录 / 搜索 / 书签共用，默认收起）
        self.toc = TocPanel(self)
        self.search = SearchPanel(self)
        self.bookmarks = BookmarkPanel(self)
        self.side = QStackedWidget(self)
        self.side.addWidget(self.toc)
        self.side.addWidget(self.search)
        self.side.addWidget(self.bookmarks)
        self.side.setVisible(False)
        content = QWidget(self)
        content_lay = QHBoxLayout(content)
        content_lay.setContentsMargins(0, 0, 0, 0)
        content_lay.setSpacing(0)
        content_lay.addWidget(self.stack, 1)
        content_lay.addWidget(self.side)
        root.addWidget(content, 1)

        # 托盘：用自己实现的 Win32 版本，add() 会返回明确的成功/失败，
        # 这样「能不能隐藏窗口」才有依据（Qt 的版本会在打包版上静默失败）。
        self.tray = Win32Tray(self)
        self.tray.sig_show.connect(self.show_from_tray)
        self.tray.sig_quit.connect(self.quit_app)
        self.tray.sig_menu.connect(self._show_tray_menu)
        self._enable_tray = enable_tray
        self._tray_menu = self._build_tray_menu()

        # 信号
        self.titlebar.sig_minimize.connect(self.hide_to_tray)
        self.titlebar.sig_maximize.connect(self.toggle_maximize)
        self.titlebar.sig_close.connect(self.close)
        self.shelf.sig_open_book.connect(self.open_book)
        self.shelf.sig_status.connect(self.show_status)
        self.reader.sig_status.connect(self.show_status)
        self.reader.sig_progress.connect(self._on_progress)
        self.toc.sig_jump.connect(self._on_toc_jump)
        self.toc.sig_close.connect(self.close_side)
        self.search.sig_jump.connect(self._on_search_jump)
        self.search.sig_close.connect(self.close_side)
        self.bookmarks.sig_jump.connect(self._on_bookmark_jump)
        self.bookmarks.sig_add.connect(self.add_bookmark)
        self.bookmarks.sig_edit.connect(self._edit_bookmark)
        self.bookmarks.sig_delete.connect(self._delete_bookmark)
        self.bookmarks.sig_close.connect(self.close_side)

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
    def _tray_usable(self) -> bool:
        """托盘图标是否真的可用。不可用时绝不能把窗口藏起来。"""
        try:
            return bool(self.tray.isVisible())
        except Exception:                       # noqa: BLE001
            return False

    # ------------------------------------------------------------ 托盘菜单
    def _build_tray_menu(self):
        from PySide6.QtGui import QAction
        from PySide6.QtWidgets import QMenu

        menu = QMenu(self)
        act_show = QAction("显示主窗口", menu)
        act_show.triggered.connect(self.show_from_tray)
        menu.addAction(act_show)

        self._menu_recent = menu.addMenu("最近阅读")
        self._menu_recent.aboutToShow.connect(self._fill_recent_menu)

        menu.addSeparator()
        act_settings = QAction("偏好设置…", menu)
        act_settings.triggered.connect(self.open_settings)
        menu.addAction(act_settings)

        menu.addSeparator()
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_app)
        menu.addAction(act_quit)
        return menu

    def _fill_recent_menu(self):
        from PySide6.QtGui import QAction

        self._menu_recent.clear()
        books = self.library.list_books() or []
        if not books:
            act = QAction("（暂无记录）", self._menu_recent)
            act.setEnabled(False)
            self._menu_recent.addAction(act)
            return
        for b in books[:5]:
            pct = b.get("percent") or 0.0
            act = QAction("%s  —  %.1f%%" % (b["title"], pct), self._menu_recent)
            act.triggered.connect(
                lambda _=False, bid=int(b["id"]): self._open_from_tray(bid))
            self._menu_recent.addAction(act)

    def _open_from_tray(self, book_id: int):
        self.show_from_tray()
        self.open_book(book_id)

    def _show_tray_menu(self, pos):
        self._tray_menu.popup(pos)

    def showEvent(self, ev):
        super().showEvent(ev)
        # 托盘要 HWND 才能接收回调，所以等窗口真正显示后再注册。
        if self._enable_tray and not self.tray.isVisible():
            ok = self.tray.attach(self)
            if not ok:
                self._tray_error = self.tray.last_error
                self._report_tray_failure()

    def _report_tray_failure(self):
        """托盘注册失败时说清楚原因：弹窗 + 写文件（窗口标题会被书名覆盖，
        不能指望用户在那里看到错误码）。"""
        import os
        import sys

        err = getattr(self, "_tray_error", None)
        hint = ""
        if err == 5:
            hint = (
                "\n\n错误码 5 = ERROR_ACCESS_DENIED（权限不足）。\n"
                "Windows 不允许「与资源管理器权限级别不一致的进程」往托盘里加图标。\n"
                "常见原因：\n"
                "  · 从别的程序的「打开」按钮启动（继承了受限令牌）\n"
                "  · 本程序以管理员身份运行，而资源管理器是普通权限（或反过来）\n"
                "建议：关掉本程序，直接在「文件资源管理器」里双击 exe 再试一次。")
        elif err in (1400, 1407):
            hint = "\n\n错误码 %s = 窗口句柄无效，说明注册时机太早。" % err
        detail = [
            "系统托盘图标注册失败。",
            "",
            "Win32 错误码：%s" % err,
            "Shell_NotifyIcon(NIM_ADD) 返回：False",
            "窗口句柄：%s" % int(self.winId()),
        ]
        text = "\n".join(detail)

        # 1) 写到程序目录，方便把文件发回来
        try:
            base = (os.path.dirname(os.path.abspath(sys.executable))
                    if getattr(sys, "frozen", False)
                    else os.path.dirname(os.path.dirname(os.path.dirname(
                        os.path.abspath(__file__)))))
            with open(os.path.join(base, "托盘诊断.txt"), "w", encoding="utf-8") as f:
                f.write(text + hint + "\n")
        except OSError:
            pass

        # 2) 弹窗。没有托盘时 ESC 只会最小化，用户需要知道这一点
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(
                self, "托盘不可用",
                text + hint + "\n\n因此 ESC 只能最小化到任务栏（任务栏会保留图标），\n"
                       "关闭按钮可以正常退出程序。")
        except Exception:                   # noqa: BLE001
            pass

    def hide_to_tray(self):
        """ESC / 标题栏最小化按钮：收进托盘或最小化到任务栏（可配）。

        注意：这里**不包括**关闭按钮。关闭按钮必须能真正退出程序——
        之前把 ✕ 也接到这里，结果关闭按钮只会把窗口最小化，
        用户除了任务管理器没有任何办法退出。
        """
        from PySide6.QtWidgets import QApplication
        # 保险：任何情况下都不允许「最后一个窗口隐藏 = 退出进程」。
        inst = QApplication.instance()
        if inst is not None:
            inst.setQuitOnLastWindowClosed(False)

        self._save_geometry()

        # explorer 重启过的话图标会丢，这里给一次机会重新注册
        if not self.tray.isVisible() and self._enable_tray:
            self.tray.attach(self)

        action = self.settings.get("window.escAction", "auto")
        usable = self._tray_usable()
        # auto：托盘真的注册成功才收进托盘，否则退化为最小化（任务栏一定有图标）
        if action == "minimize" or (action == "auto" and not usable) or not usable:
            self.showMinimized()
            return

        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.notify(
                "已收进系统托盘，程序仍在后台运行。\n"
                "托盘图标可能被 Windows 收进任务栏右下角的「^」溢出区，\n"
                "再次双击启动图标也能把窗口叫回来。")

    def show_from_tray(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self.reader.setFocus()

    def quit_app(self):
        self._stop_worker()
        self.reader.close_book()
        self._save_geometry()
        self.tray.hide()
        from PySide6.QtWidgets import QApplication
        QApplication.quit()

    def _stop_worker(self, timeout_ms: int = 3000) -> None:
        """退出前等工作线程收尾，避免 QThread 在运行中被销毁。"""
        w = self._chapter_worker
        if w is not None and w.isRunning():
            w.wait(timeout_ms)
        self._chapter_worker = None

    # ------------------------------------------------------------ 文档
    def open_book(self, book_id: int):
        book = self.library.get_book(book_id)
        if not book:
            self.show_status("找不到这本书的记录")
            return
        if not book.get("exists", True):
            self.show_status("源文件已不存在：%s" % book["file_path"])
            return

        # EPUB：先确保有纯文本缓存，再让阅读器读缓存（阅读链路与 TXT 完全一致）
        read_path = book["file_path"]
        if (book.get("format") or "txt").lower() == "epub":
            cache = self.library.epub_cache_path(int(book_id))
            # 缓存存在但章节表为空 = 上次转换没走到写库（中断、或缓存被手工拷进来）
            # 这种情况必须重转，否则目录会一直是空的。
            need_convert = (not os.path.exists(cache)
                            or not self.library.list_chapters(int(book_id)))
            if need_convert:
                if not self._convert_epub(book, cache):
                    return
                book = self.library.get_book(book_id) or book
                self.shelf.refresh()
            read_path = cache

        if self.reader.open_book(book, read_path):
            self.stack.setCurrentWidget(self.reader)
            self.titlebar.set_title(book["title"])
            self.toc.clear()
            self.search.set_target(None, [])
            self.bookmarks.clear()
            self.reader.clear_search_hits()
            # 目录延后到首帧之后加载：100 MB TXT 首次识别约 170 ms，
            # 不该挡在第一页显示之前；二次打开走缓存，几乎无感。
            QTimer.singleShot(40, self._load_toc)
        else:
            self.shelf.refresh()

    # ------------------------------------------------------------ EPUB
    def _convert_epub(self, book: dict, cache_path: str) -> bool:
        """把 EPUB 转成纯文本缓存（后台线程 + 进度条）。返回是否成功。"""
        from PySide6.QtCore import QEventLoop
        from PySide6.QtWidgets import QProgressDialog

        from .epub_worker import EpubWorker

        dlg = QProgressDialog("正在转换 EPUB：%s" % book["title"], "取消", 0, 100, self)
        dlg.setWindowTitle("EPUB 转换")
        dlg.setWindowModality(Qt.WindowModality.ApplicationModal)
        dlg.setMinimumDuration(0)
        dlg.setAutoClose(False)      # 转完自己关，避免 100% 时被当成“取消”
        dlg.setAutoReset(False)
        dlg.setValue(0)
        dlg.show()

        worker = EpubWorker(book["file_path"], cache_path, self)
        self._epub_worker = worker
        outcome = {}
        loop = QEventLoop()

        def on_progress(done, total):
            dlg.setValue(int(done * 100 / max(1, total)))

        def on_ok(result):
            outcome["result"] = result
            loop.quit()

        def on_fail(message):
            outcome["error"] = message
            loop.quit()

        worker.progressed.connect(on_progress)
        worker.finished_ok.connect(on_ok)
        worker.failed.connect(on_fail)
        dlg.canceled.connect(lambda: (worker.request_cancel(), loop.quit()))

        worker.start()
        loop.exec()
        worker.wait(5000)
        dlg.close()
        self._epub_worker = None

        result = outcome.get("result")
        if result is None:
            if "error" in outcome:
                self.show_status("EPUB 转换失败：%s" % outcome["error"])
            else:
                self.show_status("已取消转换")
            return False

        self.library.save_epub_result(int(book["id"]), result)
        self.show_status("已完成转换：%d 章" % len(result.chapters))
        return True

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
        self.toc.highlight_offset(self.reader.top_offset())
        self.reader.setFocus()

    def toggle_search(self):
        if self._side_showing(self.search):
            self.close_side()
            return
        self._load_toc()                 # 结果里要显示章节名，需要章节表
        # 章节识别是异步的，可能还没回来；但搜索本身不依赖章节，
        # 这里必须先把文档交给搜索面板，否则刚打开书就搜会提示「先打开一本书」。
        book = self.reader.book
        if book and self.reader.tf is not None:
            self.search.set_target(self.reader.tf,
                                   self.library.list_chapters(int(book["id"])))
        self.open_side(self.search)
        self.search.focus_input()

    def _load_toc(self, force: bool = False):
        """载入当前书的章节：有缓存直接显示，没有就丢给后台线程识别。

        识别本身约 170 ms（100 MB），但它是「建行索引 + 扫描」，放在主线程会把
        首屏之后的交互卡住，所以走 ChapterWorker（独立 TextFile + 独立 mmap）。
        """
        book = self.reader.book
        if not book:
            self.toc.clear()
            self.search.set_target(None, [])
            return

        cached = [] if force else self.library.list_chapters(int(book["id"]))
        if cached:
            self._apply_chapters(cached)
            return

        if self._chapter_worker is not None and self._chapter_worker.isRunning():
            return

        self.toc.set_loading()
        self.show_status("正在识别目录…")
        worker = ChapterWorker(int(book["id"]), book["file_path"],
                               book.get("encoding"), self)
        worker.finished_ok.connect(self._on_chapters_ready)
        worker.failed.connect(self._on_chapters_failed)
        self._chapter_worker = worker
        worker.start()

    def _apply_chapters(self, chapters) -> None:
        self.reader.set_chapters(chapters)
        self.toc.set_chapters(chapters)
        self.toc.highlight_offset(self.reader.top_offset())
        self.search.set_target(self.reader.tf, chapters)

    def _on_chapters_ready(self, book_id: int, chapters) -> None:
        book = self.reader.book
        if not book or int(book["id"]) != int(book_id):
            return                      # 已经换书了，丢弃过期结果
        if chapters:
            self.library.replace_chapters(int(book_id), chapters)
        rows = self.library.list_chapters(int(book_id))
        self._apply_chapters(rows)
        self.show_status("")
        if not rows and self._side_showing(self.toc):
            self.show_status("未识别到章节，可能是文件命名没有规律")

    def _on_chapters_failed(self, book_id: int, message: str) -> None:
        self.toc.set_chapters([])
        self.show_status("目录识别失败：%s" % message)

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
        elif self._side_showing(self.bookmarks):
            self.bookmarks.highlight_offset(offset)

    def toggle_reading_mode(self):
        """分页 / 滚动切换（Ctrl+M），位置保持不变。"""
        if self.reader.tf is None:
            return
        target = "paginate" if self.reader.is_scroll_mode() else "scroll"
        self.reader.set_mode(target)
        self.settings.save()
        self.show_status("阅读模式：%s" % ("滚动" if target == "scroll" else "分页"))
        self.reader.setFocus()

    # ------------------------------------------------------------ 书签
    def toggle_bookmarks(self):
        if self._side_showing(self.bookmarks):
            self.close_side()
            return
        self._load_bookmarks()
        self.open_side(self.bookmarks)
        self.bookmarks.highlight_offset(self.reader.top_offset())
        self.reader.setFocus()

    def _load_bookmarks(self):
        book = self.reader.book
        if not book:
            self.bookmarks.clear()
            return
        self.bookmarks.set_bookmarks(self.library.list_bookmarks(int(book["id"])))

    def _bookmark_excerpt(self, offset: int) -> str:
        """摘要要从当前位置往后取，不能直接用 page.text 开头（滚动模式下会偏移）。"""
        tf = self.reader.tf
        try:
            raw = tf.read_bytes(offset, 240)
            text = raw.decode(tf.encoding or "utf-8", "ignore")
        except (LookupError, AttributeError):
            text = ""
        return " ".join(text.split())[:60]

    def add_bookmark(self):
        if self.reader.tf is None or self.reader.book is None:
            return
        book_id = int(self.reader.book["id"])
        offset = self.reader.top_offset()

        existing = self.library.find_bookmark_near(book_id, offset)
        if existing:
            self._load_bookmarks()
            if not self._side_showing(self.bookmarks):
                self.open_side(self.bookmarks)
            self.bookmarks.highlight_offset(offset)
            self.show_status("此处已有书签")
            return

        excerpt = self._bookmark_excerpt(offset)
        chapter = self.reader.current_chapter_title() or ""
        self.library.add_bookmark(book_id, offset, chapter, excerpt)
        self._load_bookmarks()
        if not self._side_showing(self.bookmarks):
            self.open_side(self.bookmarks)
        self.bookmarks.highlight_offset(offset)
        self.show_status("已添加书签：%s" % (excerpt[:24] or "(空)"))

    def _edit_bookmark(self, bookmark_id: int):
        book = self.reader.book
        if not book:
            return
        rows = self.library.list_bookmarks(int(book["id"]))
        row = next((r for r in rows if int(r["id"]) == int(bookmark_id)), None)
        if row is None:
            return
        from PySide6.QtWidgets import QInputDialog
        text, ok = QInputDialog.getMultiLineText(
            self, "编辑备注", "备注（可为空）：", row.get("note") or "")
        if ok:
            self.library.update_bookmark_note(int(bookmark_id), text)
            self._load_bookmarks()

    def _delete_bookmark(self, bookmark_id: int):
        from PySide6.QtWidgets import QMessageBox
        ans = QMessageBox.question(
            self, "删除书签", "确定删除这个书签吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if ans == QMessageBox.StandardButton.Yes:
            self.library.delete_bookmark(int(bookmark_id))
            self._load_bookmarks()

    def _on_bookmark_jump(self, offset: int):
        if self.reader.tf is None:
            return
        self.reader.goto_offset(offset, align_line=True)
        self.reader.setFocus()

    # ------------------------------------------------------------ 设置
    def open_settings(self):
        from .settings_dialog import SettingsDialog
        if self._settings_dlg is None:
            dlg = SettingsDialog(self.settings, self)
            dlg.sig_changed.connect(self.apply_settings_live)
            dlg.sig_pick_screen.connect(self.pick_screen_color)
            dlg.sig_close.connect(self.close_settings)
            self._settings_dlg = dlg
        self._settings_dlg.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._settings_dlg.refresh()
        self._settings_dlg.show()
        self._settings_dlg.raise_()
        self._settings_dlg.activateWindow()

    def close_settings(self):
        if self._settings_dlg is not None:
            self._settings_dlg.hide()
            self.reader.setFocus()

    def apply_settings_live(self):
        """设置面板改动后即时生效：QSS、不透明度、阅读版式；模式变了就切模式。"""
        if self.reader.tf is not None:
            want = self.settings.get("reading.mode", "paginate")
            current = "scroll" if self.reader.is_scroll_mode() else "paginate"
            if want != current:
                self.reader.set_mode(want)
            else:
                self.reader.apply_appearance()
        self.apply_theme()
        self.apply_opacity()

    def pick_screen_color(self):
        """从屏幕取色：先截图、再显示遮罩，顺序不能反。"""
        from .eyedropper import Eyedropper
        shots = Eyedropper.capture()
        if not shots:
            self.show_status("无法抓取屏幕")
            return
        self._dropper = Eyedropper(shots, None)
        self._dropper.picked.connect(self._on_color_picked)
        self._dropper.cancelled.connect(lambda: self.show_status("已取消取色"))
        self._dropper.show()
        self._dropper.raise_()
        self._dropper.activateWindow()

    def _on_color_picked(self, color):
        self.settings.set("appearance.bgColor", color.name())
        self.settings.save()
        if self._settings_dlg is not None:
            self._settings_dlg.refresh()
        self.apply_settings_live()
        self.show_status("背景色已设为 %s" % color.name().upper())

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
        if ctrl and k == Qt.Key.Key_B:
            if in_reader:
                if shift:
                    self.toggle_bookmarks()
                else:
                    self.add_bookmark()
            ev.accept()
            return
        if ctrl and k == Qt.Key.Key_M:
            if in_reader:
                self.toggle_reading_mode()
            ev.accept()
            return
        if k == Qt.Key.Key_Comma and ctrl:
            self.open_settings()
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
        """关闭窗口：托盘可用才收进托盘，否则**真正退出**。

        绝不能出现「点了 ✕ 程序还在后台、又没有任何入口」的状态——
        用户只能去任务管理器杀进程，这是最糟的体验。
        """
        if self._tray_usable() and self.settings.get("window.escAction", "auto") in ("tray", "auto"):
            ev.ignore()
            self._save_geometry()
            self.hide()
            return
        ev.accept()
        self.quit_app()
