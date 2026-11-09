# -*- coding: utf-8 -*-
"""书架业务层：导入、列表、进度、书签。"""
import os
import sqlite3
import time
from typing import Dict, List, Optional

from ..config import COVER_DIR, SUPPORTED_EXTS
from .db import connect, init_db
from .textfile import probe_encoding


class Library:
    def __init__(self, db_path: Optional[str] = None):
        self.conn = connect(db_path) if db_path else connect()
        init_db(self.conn)

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
        encoding = None
        if fmt == "txt":
            try:
                encoding, _ = probe_encoding(path)
            except OSError:
                encoding = "utf-8"
        now = int(time.time())
        cur = self.conn.execute(
            """INSERT INTO book (file_path, file_size, format, title, encoding,
                                 added_at, last_read_at, missing)
               VALUES (?, ?, ?, ?, ?, ?, NULL, 0)""",
            (path, os.path.getsize(path), fmt, title, encoding, now))
        self.conn.commit()
        return int(cur.lastrowid)

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
