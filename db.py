# db.py
import sqlite3
import time
from pathlib import Path
from typing import Optional, List


class DB:
    """
    Небольшая обёртка над SQLite для таблицы `seen`.
    Методы:
      - has_seen(msg_unique) -> bool
      - upsert_seen(...)
      - get_columns() -> List[str] (для debug)
    """
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._ensure_schema()

    def _conn(self):
        return sqlite3.connect(self.db_path)

    def _ensure_schema(self):
        with self._conn() as conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS seen (
                msg_unique TEXT PRIMARY KEY,
                channel TEXT,
                msg_id INTEGER,
                status TEXT,
                score INTEGER,
                pos_sum INTEGER,
                neg_sum INTEGER,
                matches TEXT,
                raw_text TEXT,
                first_seen_ts INTEGER
            )
            """)
            conn.commit()

    def has_seen(self, msg_unique: str) -> bool:
        q = "SELECT 1 FROM seen WHERE msg_unique=? LIMIT 1"
        with self._conn() as conn:
            cur = conn.execute(q, (msg_unique,))
            return cur.fetchone() is not None

    def upsert_seen(
        self,
        msg_unique: str,
        channel: str,
        msg_id: int,
        status: str,
        score: Optional[int],
        pos_sum: int,
        neg_sum: int,
        matches_json: str,
        raw_text: str,
        first_seen_ts: Optional[int] = None,
    ) -> None:
        if first_seen_ts is None:
            first_seen_ts = int(time.time())
        q = (
            "INSERT OR REPLACE INTO seen("
            "msg_unique, channel, msg_id, status, score, pos_sum, neg_sum, matches, raw_text, first_seen_ts"
            ") VALUES(?,?,?,?,?,?,?,?,?,?)"
        )
        with self._conn() as conn:
            conn.execute(
                q,
                (
                    msg_unique,
                    channel,
                    msg_id,
                    status,
                    score,
                    pos_sum,
                    neg_sum,
                    matches_json,
                    raw_text,
                    first_seen_ts,
                ),
            )
            conn.commit()

    def get_columns(self) -> List[str]:
        with self._conn() as conn:
            cur = conn.execute("PRAGMA table_info(seen)")
            return [t[1] for t in cur.fetchall()]
