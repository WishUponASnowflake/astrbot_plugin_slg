# domain/entities.py
from dataclasses import dataclass
from dataclasses import dataclass
from typing import Dict, List, Optional, Literal, Tuple

NodeType = Literal["CITY", "PASS", "RESOURCE"]
Gate = Literal["北门", "东门", "西门", "南门", "西北门"]  # 你要严控就只留北/东/西
MILESTONES: List[str] = ["前沿", "箭楼", "外城门"]

@dataclass(frozen=True)
class City:
    name: str
    province: str
    ntype: NodeType
    capital: bool = False

@dataclass
class MapGraph:
    cities: Dict[str, City]                             # 城市元数据
    lines: Dict[str, Dict[Gate, str]]                   # 城市 -> {门 -> 邻城}
    positions: Dict[str, Tuple[int, int]]               # 城市 -> (x, y)
