from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

from . import settings

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS sync_blobs (
    user_id TEXT PRIMARY KEY,
    revision INTEGER NOT NULL,
    envelope TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    global _CONN
    db_path = Path(path or settings.DATABASE_PATH)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def get_conn() -> sqlite3.Connection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            _CONN = connect()
        return _CONN


def reset_for_tests(path: Path) -> None:
    global _CONN
    with _LOCK:
        if _CONN is not None:
            _CONN.close()
            _CONN = None
        settings.DATABASE_PATH = path
        _CONN = connect(path)


def lock() -> threading.RLock:
    return _LOCK
