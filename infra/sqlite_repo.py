# infra/sqlite_repo.py
import sqlite3
from pathlib import Path
from typing import Optional
from ..domain.ports import StateRepositoryPort


class SQLiteStateRepository(StateRepositoryPort):
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.execute("PRAGMA journal_mode=WAL;")

    def init_schema(self) -> None:
        self._conn.execute("""
        CREATE TABLE IF NOT EXISTS kv (
            k TEXT PRIMARY KEY,
            v TEXT
        );
        """)
        self._conn.commit()

    def get(self, key: str) -> Optional[str]:
        cur = self._conn.execute("SELECT v FROM kv WHERE k=?", (key,))
        row = cur.fetchone()
        return row[0] if row else None

    def set(self, key: str, val: str) -> None:
        self._conn.execute(
            "INSERT INTO kv(k, v) VALUES(?, ?) ON CONFLICT(k) DO UPDATE SET v=excluded.v;",
            (key, val),
        )
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass
