import sqlite3
from pathlib import Path
from typing import List, Tuple, Optional


class MemoryStore:
    def __init__(self, db_path: str = "session.db") -> None:
        self.db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    session_id TEXT PRIMARY KEY,
                    summary TEXT NOT NULL,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    fact TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            conn.commit()

    def add_message(self, session_id: str, role: str, content: str) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO messages (session_id, role, content)
                VALUES (?, ?, ?)
                """,
                (session_id, role, content),
            )
            conn.commit()
            return int(cur.lastrowid)

    def get_recent_messages(
        self, session_id: str, limit: int = 6
    ) -> List[Tuple[int, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()

        # Return oldest -> newest
        return [(int(r["id"]), str(r["role"]), str(r["content"])) for r in reversed(rows)]

    def get_messages_after_id(
        self, session_id: str, min_id: int
    ) -> List[Tuple[int, str, str]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE session_id = ? AND id > ?
                ORDER BY id ASC
                """,
                (session_id, min_id),
            ).fetchall()

        return [(int(r["id"]), str(r["role"]), str(r["content"])) for r in rows]

    def count_messages(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS cnt
                FROM messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return int(row["cnt"]) if row else 0

    def get_summary(self, session_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT summary
                FROM summaries
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        return str(row["summary"]) if row else ""

    def upsert_summary(self, session_id: str, summary: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO summaries (session_id, summary, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(session_id)
                DO UPDATE SET summary=excluded.summary, updated_at=CURRENT_TIMESTAMP
                """,
                (session_id, summary),
            )
            conn.commit()

    def add_fact(self, session_id: str, fact: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO facts (session_id, fact)
                VALUES (?, ?)
                """,
                (session_id, fact),
            )
            conn.commit()

    def get_facts(self, session_id: str, limit: int = 20) -> List[str]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT fact
                FROM facts
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, limit),
            ).fetchall()
        return [str(r["fact"]) for r in reversed(rows)]

    def get_latest_message_id(self, session_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT MAX(id) AS max_id
                FROM messages
                WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()
        if not row or row["max_id"] is None:
            return 0
        return int(row["max_id"])

    def get_message_by_id(self, session_id: str, msg_id: int) -> Optional[Tuple[int, str, str]]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, role, content
                FROM messages
                WHERE session_id = ? AND id = ?
                """,
                (session_id, msg_id),
            ).fetchone()
        if not row:
            return None
        return (int(row["id"]), str(row["role"]), str(row["content"]))