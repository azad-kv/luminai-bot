import os
import shutil
import sqlite3
from pathlib import Path
from typing import List, Tuple

from dotenv import load_dotenv

from conversation_memory import ConversationMemoryIndex

load_dotenv()

DB_PATH = os.getenv("SESSION_DB_PATH", "session.db")
MEMORY_DIR = os.getenv("MEMORY_INDEX_DIR", "memory_index")
MEMORY_EMBEDDING_PROVIDER = os.getenv("MEMORY_EMBEDDING_PROVIDER", "gemini").strip().lower()


def load_messages(db_path: str) -> List[Tuple[int, str, str, str]]:
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Missing database file: {db_path}")

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """
            SELECT id, session_id, role, content
            FROM messages
            ORDER BY id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    return [
        (int(r["id"]), str(r["session_id"]), str(r["role"]), str(r["content"]))
        for r in rows
    ]


def reset_memory_dir(memory_dir: str) -> None:
    path = Path(memory_dir)
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def main() -> None:
    print(f"Reading messages from: {DB_PATH}")
    print(f"Rebuilding memory index in: {MEMORY_DIR}")
    print(f"Embedding provider: {MEMORY_EMBEDDING_PROVIDER}")

    messages = load_messages(DB_PATH)
    if not messages:
        print("No messages found in session.db. Nothing to reindex.")
        return

    reset_memory_dir(MEMORY_DIR)

    memory_index = ConversationMemoryIndex(
        memory_dir=MEMORY_DIR,
        embedding_provider=MEMORY_EMBEDDING_PROVIDER,
    )

    added = 0
    skipped = 0

    for msg_id, session_id, role, content in messages:
        text = (content or "").strip()
        if not text:
            skipped += 1
            continue

        memory_index.add_memory(
            session_id=session_id,
            message_id=msg_id,
            role=role,
            content=text,
        )
        added += 1

        if added % 25 == 0:
            print(f"Indexed {added} messages...")

    print("\nDone.")
    print(f"Indexed messages: {added}")
    print(f"Skipped empty messages: {skipped}")
    print(f"FAISS index: {Path(MEMORY_DIR) / 'memory.faiss'}")
    print(f"Metadata: {Path(MEMORY_DIR) / 'memory_chunks.jsonl'}")


if __name__ == "__main__":
    main()