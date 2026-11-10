# -*- coding: utf-8 -*-
"""书架业务层：导入、列表、进度、书签。"""
import os
import sqlite3
import time
from typing import Dict, List, Optional

from ..config import COVER_DIR, SUPPORTED_EXTS, TEXT_CACHE_DIR
from .db import connect, init_db
from . import toc as toc_rules
from .epub import cache_name as epub_cache_name
from .epub import read_meta as read_epub_meta
from .textfile import TextFile, probe_encoding


class Library:
    def __init__(self, db_path: Optional[str] = None):
        self.conn = connect(db_path) if db_path else connect()
        init_db(self.conn)
        # EPUB 的纯文本缓存放在文本缓存目录；测试用临时库时也隔离到库文件旁边
        if db_path:
            self.text_cache_dir = os.path.join(os.path.dirname(os.path.abspath(db_path)),
                                               "text_cache")
        else:
            self.text_cache_dir = TEXT_CACHE_DIR
        os.makedirs(self.text_cache_dir, exist_ok=True)

    # ------------------------------------------------------------ 书籍
    def add_file(self, path: str) -> Optional[int]:
        """导入一个文件，返回 book_id（已存在则返回原 id）。"""
        path = os.path.abspath(path)
        if not os.path.isfile(path):
            return None
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED_EXTS:
            return None

        row = self.conn.execute(
            "SELECT id FROM book WHERE file_path = ?", (path,)).fetchone()
        if row:
            self.conn.execute(
                "UPDATE book SET missing = 0, file_size = ? WHERE id = ?",
                (os.path.getsize(path), row["id"]))
            self.conn.commit()
            return int(row["id"])

        fmt = ext.lstrip(".")
        title = os.path.splitext(os.path.basename(path))[0]
        author = None
        encoding = None
        if fmt == "txt":
            try:
                encoding, _ = probe_encoding(path)
            except OSError:
                encoding = "utf-8"
        else:
            # EPUB：从 OPF 里读真实书名/作者，比文件名可靠
            try:
                meta_title, meta_author = read_epub_meta(path)
                title = meta_title or title
                author = meta_author or None
            except Exception:                       # noqa: BLE001
                pass
        now = int(time.time())
        cur = self.conn.execute(
            """INSERT INTO book (file_path, file_size, format, title, author, encoding,
                                 added_at, last_read_at, missing)
               VALUES (?, ?, ?, ?, ?, ?, ?, NULL, 0)""",
            (path, os.path.getsize(path), fmt, title, author, encoding, now))
        self.conn.commit()
        return int(cur.lastrowid)

    # ------------------------------------------------------------ EPUB
    def epub_cache_path(self, book_id: int) -> str:
        """EPUB 转换后的纯文本缓存路径（按 book_id 派生，不用改表结构）。"""
        return os.path.join(self.text_cache_dir, epub_cache_name(book_id))

    def save_epub_result(self, book_id: int, result) -> None:
        """把转换结果落库：章节表 + 书名/作者 + 字符数。"""
        self.replace_chapters(book_id, result.chapters)
        self.conn.execute(
            "UPDATE book SET title = COALESCE(NULLIF(?, ''), title),"
            " author = COALESCE(NULLIF(?, ''), author),"
            " encoding = 'utf-8', char_count = ? WHERE id = ?",
            (result.title, result.author, result.chars, book_id))
        self.conn.commit()

    def set_book_meta(self, book_id: int, title=None, author=None) -> None:
        if title:
            self.conn.execute("UPDATE book SET title = ? WHERE id = ?", (title, book_id))
        if author:
            self.conn.execute("UPDATE book SET author = ? WHERE id = ?", (author, book_id))
        self.conn.commit()

    def list_books(self) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT b.*, p.offset, p.percent, p.updated_at
                 FROM book b LEFT JOIN progress p ON p.book_id = b.id
                ORDER BY COALESCE(b.last_read_at, 0) DESC, b.added_at DESC"""
        ).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["exists"] = os.path.isfile(d["file_path"])
            d["percent"] = d.get("percent") or 0.0
            out.append(d)
        return out

    def get_book(self, book_id: int) -> Optional[Dict]:
        row = self.conn.execute("SELECT * FROM book WHERE id = ?", (book_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["exists"] = os.path.isfile(d["file_path"])
        return d

    def remove_book(self, book_id: int) -> None:
        self.conn.execute("DELETE FROM book WHERE id = ?", (book_id,))
        self.conn.commit()

    # ------------------------------------------------------------ 进度
    def get_progress(self, book_id: int) -> Dict:
        row = self.conn.execute(
            "SELECT * FROM progress WHERE book_id = ?", (book_id,)).fetchone()
        return dict(row) if row else {"book_id": book_id, "offset": 0,
                                      "percent": 0.0, "chapter_id": None}

    def save_progress(self, book_id: int, offset: int, percent: float,
                      chapter_id: Optional[int] = None) -> None:
        now = int(time.time())
        self.conn.execute(
            """INSERT INTO progress (book_id, offset, percent, chapter_id, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(book_id) DO UPDATE SET
                 offset = excluded.offset,
                 percent = excluded.percent,
                 chapter_id = excluded.chapter_id,
                 updated_at = excluded.updated_at""",
            (book_id, offset, percent, chapter_id, now))
        self.conn.execute("UPDATE book SET last_read_at = ? WHERE id = ?", (now, book_id))
        self.conn.commit()

    # ------------------------------------------------------------ 目录
    def replace_chapters(self, book_id: int, chapters) -> int:
        """整体替换一本书的章节表（识别结果按书缓存，重识别时覆盖）。"""
        rows = [(book_id, i, c.level, c.title, c.offset)
                for i, c in enumerate(chapters)]
        cur = self.conn.cursor()
        cur.execute("DELETE FROM chapter WHERE book_id = ?", (book_id,))
        cur.executemany(
            "INSERT INTO chapter (book_id, idx, level, title, start_off) VALUES (?,?,?,?,?)",
            rows)
        cur.execute("UPDATE book SET chapter_count = ? WHERE id = ?",
                    (len(rows), book_id))
        self.conn.commit()
        return len(rows)

    def list_chapters(self, book_id: int) -> List[Dict]:
        rows = self.conn.execute(
            """SELECT idx, level, title, start_off FROM chapter
                WHERE book_id = ? ORDER BY idx""", (book_id,)).fetchall()
        return [dict(r) for r in rows]

    def ensure_chapters(self, book: Dict, force: bool = False) -> List[Dict]:
        """取章节表；没有就现场识别并缓存。

        TXT 100 MB 实测：建索引 104 ms + 识别 66 ms，可以同步跑；EPUB 的目录
        由解析阶段直接产出（M4）。
        """
        bid = int(book["id"])
        if not force:
            cached = self.list_chapters(bid)
            if cached:
                return cached
        if (book.get("format") or "txt").lower() != "txt":
            return []
        try:
            tf = TextFile(book["file_path"], encoding=book.get("encoding")).open()
        except OSError:
            return []
        try:
            chapters = toc_rules.detect(tf)
        finally:
            tf.close()
        if chapters:
            self.replace_chapters(bid, chapters)
        return self.list_chapters(bid)

    # ------------------------------------------------------------ 书签
    def add_bookmark(self, book_id: int, offset: int, chapter: str,
                     excerpt: str, note: str = "") -> int:
        cur = self.conn.execute(
            """INSERT INTO bookmark (book_id, offset, chapter_title, excerpt, note, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (book_id, offset, chapter, excerpt, note, int(time.time())))
        self.conn.commit()
        return int(cur.lastrowid)

    def list_bookmarks(self, book_id: int) -> List[Dict]:
        rows = self.conn.execute(
            "SELECT * FROM bookmark WHERE book_id = ? ORDER BY offset",
            (book_id,)).fetchall()
        return [dict(r) for r in rows]

    def delete_bookmark(self, bookmark_id: int) -> None:
        self.conn.execute("DELETE FROM bookmark WHERE id = ?", (bookmark_id,))
        self.conn.commit()

    def close(self) -> None:
        try:
            self.conn.close()
        except sqlite3.Error:
            pass
