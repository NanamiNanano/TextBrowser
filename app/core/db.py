# -*- coding: utf-8 -*-
"""SQLite 存储：书籍、章节、进度、书签。"""
import sqlite3
from typing import Optional

from ..config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS book (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  file_path     TEXT NOT NULL UNIQUE,
  file_size     INTEGER NOT NULL DEFAULT 0,
  file_hash     TEXT,
  format        TEXT NOT NULL DEFAULT 'txt',
  title         TEXT NOT NULL,
  author        TEXT,
  encoding      TEXT,
  char_count    INTEGER,
  chapter_count INTEGER,
  cover_path    TEXT,
  added_at      INTEGER NOT NULL,
  last_read_at  INTEGER,
  missing       INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS chapter (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id    INTEGER NOT NULL REFERENCES book(id) ON DELETE CASCADE,
  idx        INTEGER NOT NULL,
  level      INTEGER NOT NULL DEFAULT 1,
  title      TEXT NOT NULL,
  start_off  INTEGER NOT NULL,
  UNIQUE(book_id, idx)
);

CREATE TABLE IF NOT EXISTS progress (
  book_id    INTEGER PRIMARY KEY REFERENCES book(id) ON DELETE CASCADE,
  offset     INTEGER NOT NULL,
  percent    REAL NOT NULL DEFAULT 0,
  chapter_id INTEGER,
  updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS bookmark (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id       INTEGER NOT NULL REFERENCES book(id) ON DELETE CASCADE,
  offset        INTEGER NOT NULL,
  chapter_title TEXT,
  excerpt       TEXT,
  note          TEXT,
  created_at    INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_bookmark_book ON bookmark(book_id, offset);
CREATE INDEX IF NOT EXISTS idx_chapter_book  ON chapter(book_id, start_off);
"""


def connect(path: str = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
