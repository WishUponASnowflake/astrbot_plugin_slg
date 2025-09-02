from typing import Dict, List
from enum import Enum

# 建筑与资源映射
BUILDING_TO_RESOURCE = {
    "farm": "grain",  # 农田 -> 粮食
    "bank": "gold",  # 钱庄 -> 金钱
    "quarry": "stone",  # 采石场 -> 石头
    "barracks": "troops",  # 军营 -> 军队
}
# 中文别名映射（命令里用）
BUILDING_ALIASES = {
    "农田": "farm",
    "钱庄": "bank",
    "采石场": "quarry",
    "军营": "barracks",
}
RESOURCE_CN = {"grain": "粮食", "gold": "金钱", "stone": "石头", "troops": "军队"}

MAX_LEVEL = 10
MINUTE = 60


# 抽卡结果状态
class DrawResultStatus(Enum):
    SUCCESS = "success"
    NOT_ENOUGH_RESOURCES = "not_enough_resources"
    ALL_CHARACTERS_COLLECTED = "all_characters_collected"


# 每分钟产出（索引=等级，0档不用）

# === Rebalanced numbers targeting ~2.3 days ===

# 每分钟产出（保持原表）
PRODUCTION_PER_MIN: Dict[str, List[int]] = {
    "grain": [0, 8, 12, 18, 26, 35, 45, 57, 71, 86, 102],
    "gold": [0, 5, 8, 11, 15, 20, 26, 33, 42, 53, 65],
    "stone": [0, 3, 6, 9, 14, 18, 24, 32, 41, 51, 63],
    "troops": [0, 2, 2, 3, 5, 6, 9, 12, 17, 23, 30],
}


# 资源上限（已调整：在等级 L 时可攒满升级到 L+1 所需的“该资源”×1.05）
CAPACITY_PER_LEVEL: Dict[str, List[int]] = {
    "grain": [0, 972, 1602, 2412, 3384, 4518, 5796, 7254, 8856, 10890, 12924],
    "gold": [0, 810, 1386, 2106, 2916, 3870, 5004, 6300, 7740, 9360, 10980],
    "stone": [0, 1134, 2016, 3078, 4266, 5652, 7182, 8892, 10728, 12744, 14760],
    "troops": [0, 360, 540, 720, 972, 1386, 1854, 2412, 3060, 3798, 4536],
}


# 升级成本：到达目标等级 L 的一次性成本（index=L）
# 固定石头成本（等比缩放并四舍五入到 10）
UPGRADE_STONE_COST: Dict[str, List[int]] = {
    "farm": [0, 0, 170, 340, 510, 730, 980, 1280, 1620, 2050, 2560],
    "bank": [0, 0, 210, 380, 600, 850, 1150, 1490, 1880, 2300, 2820],
    "quarry": [0, 0, 260, 470, 730, 1020, 1370, 1750, 2180, 2650, 3160],
    "barracks": [0, 0, 300, 510, 770, 1070, 1410, 1790, 2220, 2690, 3200],
}

# 资源自身成本（等比缩放并四舍五入到 10）
# 注意：采石场的石头成本 = 上面固定石头成本 + 这里 stone 的自身成本
UPGRADE_RESOURCE_COST: Dict[str, List[int]] = {
    "grain": [0, 0, 510, 850, 1280, 1790, 2390, 3070, 3840, 4690, 5760],
    "gold": [0, 0, 430, 730, 1110, 1540, 2050, 2650, 3330, 4100, 4950],
    "stone": [0, 0, 340, 600, 900, 1240, 1620, 2050, 2520, 3030, 3580],
    "troops": [0, 0, 130, 210, 340, 510, 730, 980, 1280, 1620, 2010],
}

# === 队伍与角色 ===
TEAM_COUNT = 3
TEAM_SLOTS = 3
TEAM_BASE_TROOPS = 400  # 每支队伍基础兵力上限
TROOPS_PER_LEVEL = 200  # 每个角色可携带 = 角色等级 * 200
CHAR_LEVEL_MAX = 7  # 角色最高 7 级

# 角色升级消耗：线性区间（到达目标等级 T 的一次性成本；T=2..7）
CHAR_LEVEL_UP_COST_RANGE = {
    "gold": (10, 1400),
    "grain": (10, 700),
    "stone": (0, 0),
    "troops": (10, 700),
}

# === 同盟 ===
ALLIANCE_MAX_MEMBERS = 20

# === 攻城 ===
SIEGE_WINDOW_MINUTES = 30  # 攻城窗口
SIEGE_EDGE_MINUTES = 5  # 每条路段默认行军耗时（分钟）
# 达标阈值：取 30 分钟总攻城点数下限作为胜利门槛
SIEGE_CITY_REQUIRE = {
    1: 1200,  # 1200 - 1440
    2: 4000,  # 4000 - 4800
    3: 12000,  # 12000 - 14400
    4: 25600,  # 25600 - 28800
}
