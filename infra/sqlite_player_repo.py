# infra/sqlite_player_repo.py
import sqlite3, time
from pathlib import Path
from typing import Optional, Set
from ..domain.entities import Player
from ..domain.ports import PlayerRepositoryPort

DDL_PLAYERS = """
CREATE TABLE IF NOT EXISTS players(
  user_id TEXT PRIMARY KEY,
  nickname TEXT,
  created_at INTEGER,
  last_tick INTEGER,
  grain INTEGER, gold INTEGER, stone INTEGER, troops INTEGER,
  farm_level INTEGER, bank_level INTEGER, quarry_level INTEGER, barracks_level INTEGER,
  draw_count INTEGER DEFAULT 0
);
"""
DDL_CHARS = """
CREATE TABLE IF NOT EXISTS player_characters(
  user_id TEXT NOT NULL,
  name TEXT NOT NULL,
  level INTEGER NOT NULL,
  obtained_at INTEGER NOT NULL,
  PRIMARY KEY(user_id, name)
);
"""

class SQLitePlayerRepository(PlayerRepositoryPort):
    def __init__(self, db_path: Path):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")

    def init_schema(self) -> None:
        self._conn.execute(DDL_PLAYERS)
        self._conn.execute(DDL_CHARS)
        # 迁移：补列 draw_count（老库没有）
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(players)").fetchall()}
        if "draw_count" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN draw_count INTEGER DEFAULT 0;")
        self._conn.commit()

    def get_player(self, user_id: str) -> Optional[Player]:
        cur = self._conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d.setdefault("draw_count", 0)
        return Player(**d)

    def upsert_player(self, p: Player) -> None:
        self._conn.execute("""
        INSERT INTO players(user_id,nickname,created_at,last_tick,grain,gold,stone,troops,
                            farm_level,bank_level,quarry_level,barracks_level,draw_count)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          nickname=excluded.nickname,
          last_tick=excluded.last_tick,
          grain=excluded.grain, gold=excluded.gold, stone=excluded.stone, troops=excluded.troops,
          farm_level=excluded.farm_level, bank_level=excluded.bank_level,
          quarry_level=excluded.quarry_level, barracks_level=excluded.barracks_level,
          draw_count=excluded.draw_count
        """, (p.user_id, p.nickname, p.created_at, p.last_tick, p.grain, p.gold, p.stone, p.troops,
              p.farm_level, p.bank_level, p.quarry_level, p.barracks_level, p.draw_count))
        self._conn.commit()

    # —— 角色 API —— #
    def list_owned_char_names(self, user_id: str) -> Set[str]:
        cur = self._conn.execute("SELECT name FROM player_characters WHERE user_id=?", (user_id,))
        return {r[0] for r in cur.fetchall()}

    def add_character(self, user_id: str, char_name: str, level: int, obtained_at: int) -> None:
        self._conn.execute("""
        INSERT OR IGNORE INTO player_characters(user_id,name,level,obtained_at)
        VALUES(?,?,?,?)
        """, (user_id, char_name, level, obtained_at))
        self._conn.commit()

    def close(self):
        try: self._conn.close()
        except: pass
