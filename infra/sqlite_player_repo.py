# infra/sqlite_player_repo.py
import sqlite3, time
from pathlib import Path
from typing import Optional, Set
from ..domain.entities import Player
from ..domain.ports import PlayerRepositoryPort
from dataclasses import fields # 导入 fields 函数
import json

DDL_PLAYERS = """
CREATE TABLE IF NOT EXISTS players(
  user_id TEXT PRIMARY KEY,
  nickname TEXT,
  created_at INTEGER,
  last_tick INTEGER,
  grain INTEGER, gold INTEGER, stone INTEGER, troops INTEGER,
  farm_level INTEGER, bank_level INTEGER, quarry_level INTEGER, barracks_level INTEGER,
  draw_count INTEGER DEFAULT 0,
  base_city TEXT,
  base_x INTEGER,
  base_y INTEGER,
  last_move_at INTEGER DEFAULT 0
);
"""
DDL_CHARS = """
CREATE TABLE IF NOT EXISTS player_chars(
  user_id TEXT,
  name TEXT,
  level INTEGER,
  PRIMARY KEY(user_id, name)
);
"""

DDL_TEAMS = """
CREATE TABLE IF NOT EXISTS teams(
  user_id TEXT,
  team_no INTEGER,           -- 1..3
  soldiers INTEGER,          -- 当前兵力
  PRIMARY KEY(user_id, team_no)
);
"""

DDL_TEAM_SLOTS = """
CREATE TABLE IF NOT EXISTS team_slots(
  user_id TEXT,
  team_no INTEGER,
  slot_idx INTEGER,          -- 1..3
  char_name TEXT,            -- 允许为空(NULL)表示空位
  PRIMARY KEY(user_id, team_no, slot_idx)
);
"""

DDL_ALLIANCES = """
CREATE TABLE IF NOT EXISTS alliances(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT UNIQUE,
  leader_user_id TEXT,
  created_at INTEGER
);
"""

DDL_ALLIANCE_MEMBERS = """
CREATE TABLE IF NOT EXISTS alliance_members(
  alliance_id INTEGER,
  user_id TEXT UNIQUE,
  role TEXT,             -- 'leader' or 'member'
  joined_at INTEGER,
  PRIMARY KEY(user_id),
  FOREIGN KEY(alliance_id) REFERENCES alliances(id)
);
"""

DDL_SIEGES = """
CREATE TABLE IF NOT EXISTS sieges(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  alliance_id INTEGER,
  city TEXT,
  city_level INTEGER,
  start_at INTEGER,          -- 预定开战时间（epoch秒）
  created_by TEXT,
  created_at INTEGER,
  state TEXT,                -- scheduled | ongoing | done | canceled
  result TEXT                -- success | fail | NULL
);
"""

DDL_SIEGE_PARTS = """
CREATE TABLE IF NOT EXISTS siege_participants(
  siege_id INTEGER,
  user_id TEXT,
  from_city TEXT,
  path_json TEXT,            -- ["成都","绵竹","广汉",...]
  hops INTEGER,
  eta INTEGER,               -- 预计到达时间（epoch秒）
  joined_at INTEGER,
  PRIMARY KEY(siege_id, user_id)
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
        self._conn.execute(DDL_TEAMS)
        self._conn.execute(DDL_TEAM_SLOTS)
        self._conn.execute(DDL_ALLIANCES)
        self._conn.execute(DDL_ALLIANCE_MEMBERS)
        
        # 攻城相关
        self._conn.execute(DDL_SIEGES)
        self._conn.execute(DDL_SIEGE_PARTS)
        
        # players 表列迁移（之前已加过）
        cols = {r[1] for r in self._conn.execute("PRAGMA table_info(players)").fetchall()}
        if "draw_count" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN draw_count INTEGER DEFAULT 0;")
        if "base_city" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN base_city TEXT;")
        if "base_x" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN base_x INTEGER;")
        if "base_y" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN base_y INTEGER;")
        if "last_move_at" not in cols:
            self._conn.execute("ALTER TABLE players ADD COLUMN last_move_at INTEGER DEFAULT 0;")
        self._conn.commit()

    # === 基地读写 ===
    def get_base(self, user_id: str):
        cur = self._conn.execute(
            "SELECT base_city, base_x, base_y FROM players WHERE user_id=?", (user_id,)
        )
        r = cur.fetchone()
        if not r: return None
        if r[0] is None: return None
        return {"city": r[0], "x": r[1], "y": r[2]}

    def set_base(self, user_id: str, city: str, x: int, y: int):
        self._conn.execute(
            "UPDATE players SET base_city=?, base_x=?, base_y=? WHERE user_id=?",
            (city, x, y, user_id),
        )
        self._conn.commit()

    # === 迁城时间 ===
    def get_last_move_at(self, user_id: str) -> int:
        cur = self._conn.execute("SELECT last_move_at FROM players WHERE user_id=?", (user_id,))
        r = cur.fetchone()
        return 0 if not r or r[0] is None else int(r[0])

    def set_last_move_at(self, user_id: str, ts: int | None = None):
        ts = int(ts or time.time())
        self._conn.execute(
            "UPDATE players SET last_move_at=? WHERE user_id=?", (ts, user_id)
        )
        self._conn.commit()

    def get_player(self, user_id: str) -> Optional[Player]:
        cur = self._conn.execute("SELECT * FROM players WHERE user_id=?", (user_id,))
        row = cur.fetchone()
        if not row:
            return None
        d = dict(row)
        d.setdefault("draw_count", 0)
        d.setdefault("base_city", None)
        d.setdefault("base_x", None)
        d.setdefault("base_y", None)
        d.setdefault("last_move_at", 0)
        
        # 获取 Player dataclass 的所有字段名
        player_fields = {f.name for f in fields(Player)}
        
        # 过滤掉 Player 类不接受的参数
        filtered_d = {k: v for k, v in d.items() if k in player_fields}
        
        return Player(**filtered_d)

    def upsert_player(self, p: Player) -> None:
        self._conn.execute("""
        INSERT INTO players(user_id,nickname,created_at,last_tick,grain,gold,stone,troops,
                            farm_level,bank_level,quarry_level,barracks_level,draw_count,
                            base_city,base_x,base_y,last_move_at)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(user_id) DO UPDATE SET
          nickname=excluded.nickname,
          last_tick=excluded.last_tick,
          grain=excluded.grain, gold=excluded.gold, stone=excluded.stone, troops=excluded.troops,
          farm_level=excluded.farm_level, bank_level=excluded.bank_level,
          quarry_level=excluded.quarry_level, barracks_level=excluded.barracks_level,
          draw_count=excluded.draw_count,
          base_city=excluded.base_city,
          base_x=excluded.base_x,
          base_y=excluded.base_y,
          last_move_at=excluded.last_move_at
        """, (p.user_id, p.nickname, p.created_at, p.last_tick, p.grain, p.gold, p.stone, p.troops,
              p.farm_level, p.bank_level, p.quarry_level, p.barracks_level, p.draw_count,
              getattr(p, 'base_city', None), getattr(p, 'base_x', None),
              getattr(p, 'base_y', None), getattr(p, 'last_move_at', 0)))
        self._conn.commit()

    # === 角色收集/等级 ===
    def list_owned_char_names(self, user_id: str):
        cur = self._conn.execute("SELECT name FROM player_chars WHERE user_id=?", (user_id,))
        return [r[0] for r in cur.fetchall()]

    def has_char(self, user_id: str, name: str) -> bool:
        cur = self._conn.execute("SELECT 1 FROM player_chars WHERE user_id=? AND name=? LIMIT 1", (user_id, name))
        return cur.fetchone() is not None

    def add_char(self, user_id: str, name: str, level: int = 1) -> None:
        self._conn.execute(
            "INSERT OR IGNORE INTO player_chars(user_id,name,level) VALUES(?,?,?)",
            (user_id, name, level)
        )
        self._conn.commit()

    def get_char_level(self, user_id: str, name: str):
        cur = self._conn.execute("SELECT level FROM player_chars WHERE user_id=? AND name=?", (user_id, name))
        r = cur.fetchone()
        return None if r is None else int(r[0])

    def set_char_level(self, user_id: str, name: str, level: int):
        self._conn.execute("UPDATE player_chars SET level=? WHERE user_id=? AND name=?", (level, user_id, name))
        self._conn.commit()

    # === 队伍 ===
    def ensure_teams(self, user_id: str, team_count: int, slots: int):
        # 创建 1..team_count 的 team 与 1..slots 的空位
        for t in range(1, team_count + 1):
            self._conn.execute(
                "INSERT OR IGNORE INTO teams(user_id,team_no,soldiers) VALUES(?,?,0)",
                (user_id, t)
            )
            for s in range(1, slots + 1):
                self._conn.execute(
                    "INSERT OR IGNORE INTO team_slots(user_id,team_no,slot_idx,char_name) VALUES(?,?,?,NULL)",
                    (user_id, t, s)
                )
        self._conn.commit()

    def list_team_slots(self, user_id: str, team_no: int):
        cur = self._conn.execute(
            "SELECT slot_idx, char_name FROM team_slots WHERE user_id=? AND team_no=? ORDER BY slot_idx",
            (user_id, team_no)
        )
        return [(int(r[0]), r[1]) for r in cur.fetchall()]

    def set_team_slot(self, user_id: str, team_no: int, slot_idx: int, char_name: str | None):
        self._conn.execute(
            "UPDATE team_slots SET char_name=? WHERE user_id=? AND team_no=? AND slot_idx=?",
            (char_name, user_id, team_no, slot_idx)
        )
        self._conn.commit()

    def find_char_team(self, user_id: str, name: str):
        cur = self._conn.execute(
            "SELECT team_no, slot_idx FROM team_slots WHERE user_id=? AND char_name=? LIMIT 1",
            (user_id, name)
        )
        r = cur.fetchone()
        return None if r is None else (int(r[0]), int(r[1]))

    def get_team_soldiers(self, user_id: str, team_no: int) -> int:
        cur = self._conn.execute("SELECT soldiers FROM teams WHERE user_id=? AND team_no=?", (user_id, team_no))
        r = cur.fetchone()
        return 0 if r is None else int(r[0])

    def set_team_soldiers(self, user_id: str, team_no: int, soldiers: int):
        self._conn.execute("UPDATE teams SET soldiers=? WHERE user_id=? AND team_no=?", (soldiers, user_id, team_no))
        self._conn.commit()

    def close(self):
        try: self._conn.close()
        except: pass

    # ======= 同盟：查询/创建/加入/成员 =======
    def get_alliance_by_name(self, name: str):
        cur = self._conn.execute("SELECT id,name,leader_user_id,created_at FROM alliances WHERE name=?", (name,))
        r = cur.fetchone()
        return None if r is None else dict(r)

    def create_alliance(self, name: str, leader_user_id: str, created_at: int) -> int:
        cur = self._conn.execute(
            "INSERT INTO alliances(name,leader_user_id,created_at) VALUES(?,?,?)",
            (name, leader_user_id, created_at)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_user_alliance(self, user_id: str):
        cur = self._conn.execute("""
        SELECT a.id,a.name,a.leader_user_id,a.created_at, m.role, m.joined_at
        FROM alliance_members m JOIN alliances a ON a.id=m.alliance_id
        WHERE m.user_id=?
        """, (user_id,))
        r = cur.fetchone()
        return None if r is None else dict(r)

    def add_member_to_alliance(self, alliance_id: int, user_id: str, role: str, joined_at: int):
        self._conn.execute(
            "INSERT OR REPLACE INTO alliance_members(alliance_id,user_id,role,joined_at) VALUES(?,?,?,?)",
            (alliance_id, user_id, role, joined_at)
        )
        self._conn.commit()

    def remove_member_from_alliance(self, user_id: str):
        self._conn.execute("DELETE FROM alliance_members WHERE user_id=?", (user_id,))
        self._conn.commit()

    def count_alliance_members(self, alliance_id: int) -> int:
        cur = self._conn.execute("SELECT COUNT(1) FROM alliance_members WHERE alliance_id=?", (alliance_id,))
        return int(cur.fetchone()[0])

    def list_alliances(self):
        cur = self._conn.execute("""
        SELECT a.id,a.name,a.leader_user_id,a.created_at, COUNT(m.user_id) AS members
        FROM alliances a LEFT JOIN alliance_members m ON a.id=m.alliance_id
        GROUP BY a.id
        ORDER BY members DESC, a.id ASC
        """)
        return [dict(r) for r in cur.fetchall()]

    def list_alliance_members(self, alliance_id: int):
        cur = self._conn.execute("""
        SELECT user_id, role, joined_at
        FROM alliance_members
        WHERE alliance_id=?
        ORDER BY CASE role WHEN 'leader' THEN 0 ELSE 1 END, joined_at ASC
        """, (alliance_id,))
        return [dict(r) for r in cur.fetchall()]

    # === 攻城：活动 ===
    def create_siege(self, alliance_id: int, city: str, city_level: int,
                     start_at: int, created_by: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO sieges(alliance_id,city,city_level,start_at,created_by,created_at,state,result)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (alliance_id, city, city_level, start_at, created_by, int(time.time()), "scheduled", None)
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def get_active_siege_by_alliance(self, alliance_id: int):
        cur = self._conn.execute(
            "SELECT * FROM sieges WHERE alliance_id=? AND state IN ('scheduled','ongoing') "
            "ORDER BY id DESC LIMIT 1", (alliance_id,)
        )
        r = cur.fetchone()
        return None if not r else dict(zip([c[1] for c in self._conn.execute("PRAGMA table_info(sieges)")], r))

    def get_siege(self, siege_id: int):
        cur = self._conn.execute("SELECT * FROM sieges WHERE id=?", (siege_id,))
        r = cur.fetchone()
        return None if not r else dict(zip([c[1] for c in self._conn.execute("PRAGMA table_info(sieges)")], r))

    def update_siege_state(self, siege_id: int, state: str, result: str | None):
        self._conn.execute("UPDATE sieges SET state=?, result=? WHERE id=?", (state, result, siege_id))
        self._conn.commit()

    # === 攻城：参战队列 ===
    def add_siege_participant(self, siege_id: int, user_id: str,
                              from_city: str, path: list[str], hops: int, eta: int):
        self._conn.execute(
            "INSERT OR REPLACE INTO siege_participants(siege_id,user_id,from_city,path_json,hops,eta,joined_at)"
            " VALUES(?,?,?,?,?,?,?)",
            (siege_id, user_id, from_city, json.dumps(path, ensure_ascii=False), int(hops), int(eta), int(time.time()))
        )
        self._conn.commit()

    def list_siege_participants(self, siege_id: int):
        cur = self._conn.execute(
            "SELECT user_id,from_city,path_json,hops,eta,joined_at FROM siege_participants WHERE siege_id=?",
            (siege_id,)
        )
        out=[]
        for r in cur.fetchall():
            out.append({
                "user_id": r[0],
                "from_city": r[1],
                "path": json.loads(r[2]) if r[2] else [],
                "hops": int(r[3]),
                "eta": int(r[4]),
                "joined_at": int(r[5]),
            })
        return out
