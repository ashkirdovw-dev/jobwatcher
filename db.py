# db.py
import sqlite3
from pathlib import Path
from typing import Iterable, Tuple, Optional


class DB:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _ensure_schema(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sent_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    msg_id INTEGER NOT NULL,
                    chat_id INTEGER NOT NULL,
                    created_at INTEGER NOT NULL
                )
            """)
            conn.commit()

    def has_sent(self, msg_id: int, chat_id: int) -> bool:
        q = "SELECT 1 FROM sent_messages WHERE msg_id = ? AND chat_id = ? LIMIT 1"
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(q, (msg_id, chat_id))
            return cur.fetchone() is not None

    def mark_sent(self, msg_id: int, chat_id: int, ts: int):
        q = "INSERT INTO sent_messages (msg_id, chat_id, created_at) VALUES (?, ?, ?)"
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(q, (msg_id, chat_id, ts))
            conn.commit()

    def list_recent(self, limit: int = 50) -> Iterable[Tuple[int, int, int]]:
        q = "SELECT msg_id, chat_id, created_at FROM sent_messages ORDER BY created_at DESC LIMIT ?"
        with sqlite3.connect(self.db_path) as conn:
            cur = conn.execute(q, (limit,))
            yield from cur.fetchall()
