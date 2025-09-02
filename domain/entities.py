# domain/entities.py
from dataclasses import dataclass
from typing import Dict, List, Literal, Tuple

NodeType = Literal["CITY", "PASS", "RESOURCE"]
Gate = Literal["北门", "东门", "西门", "南门", "西北门"]
MILESTONES: List[str] = ["前沿", "箭楼", "外城门"]


@dataclass(frozen=True)
class City:
    name: str
    province: str
    ntype: NodeType
    capital: bool = False


@dataclass
class MapGraph:
    cities: Dict[str, City]
    lines: Dict[str, Dict[Gate, str]]
    positions: Dict[str, Tuple[int, int]]


# —— 角色 & 技能 —— #
@dataclass(frozen=True)
class Skill:
    name: str
    description: str


@dataclass(frozen=True)
class Character:
    name: str
    title: str
    background: str
    skills: List[Skill]


# —— 玩家 —— #
@dataclass
class Player:
    user_id: str
    nickname: str
    created_at: int
    last_tick: int
    grain: int
    gold: int
    stone: int
    troops: int
    farm_level: int
    bank_level: int
    quarry_level: int
    barracks_level: int
    draw_count: int = 0  # ← 新增：累计抽卡次数
