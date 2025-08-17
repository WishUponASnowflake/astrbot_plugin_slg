# domain/entities.py
from dataclasses import dataclass
from typing import Dict, List, Optional, Literal

NodeType = Literal["CITY", "PASS", "RESOURCE"]
Gate = Literal["北门", "东门", "西门"]
MILESTONES: List[str] = ["前沿", "箭楼", "外城门"]

@dataclass(frozen=True)
class City:
    name: str
    province: str        # 冀/兖/青/徐/扬/荆/豫/雍/益
    ntype: NodeType      # CITY | PASS | RESOURCE
    capital: bool = False  # 是否州府

@dataclass
class MapGraph:
    # 城市定义
    cities: Dict[str, City]
    # 战线：city -> { gate -> neighbor_city }
    lines: Dict[str, Dict[Gate, str]]
