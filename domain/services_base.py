# domain/services_base.py
from __future__ import annotations
import random
import time
from typing import Tuple

ALLOWED_PROVINCES = {"益", "扬", "冀", "兖"}


class BaseService:
    """
    依赖：
      - repo：需要 get_base/set_base/get_last_move_at/set_last_move_at
      - map_service：需要 graph()，且 graph().cities 是 {name: City}，
                     City 需有 name, province, x, y 属性（与你地图里用的 City 定义一致）
    """

    def __init__(self, repo, map_service):
        self._repo = repo
        self._map = map_service

    def _candidate_cities(self):
        g = self._map.graph()
        return [
            c
            for c in g.cities.values()
            if getattr(c, "province", None) in ALLOWED_PROVINCES
        ]

    def _city_by_name(self, name: str):
        g = self._map.graph()
        # 直接按键取；如果你做了别名映射，可以在这儿补一层 normalize
        return g.cities.get(name)

    def ensure_base(self, user_id: str) -> Tuple[bool, str]:
        base = self._repo.get_base(user_id)
        if base:
            return True, f"当前基地：{base['city']}（{base['x']},{base['y']}）"
        cand = self._candidate_cities()
        if not cand:
            return False, "没有可用的四州城市，无法分配基地"
        c = random.choice(cand)
        x, y = self._map.graph().positions.get(c.name, (0, 0))  # 获取坐标
        self._repo.set_base(user_id, c.name, int(x), int(y))
        return True, f"已为你分配基地：{c.name}（{int(x)},{int(y)}）"

    @staticmethod
    def _same_local_day(ts1: int, ts2: int) -> bool:
        import time

        d1 = time.localtime(ts1)
        d2 = time.localtime(ts2)
        return (d1.tm_year, d1.tm_yday) == (d2.tm_year, d2.tm_yday)

    def migrate(self, user_id: str, target_city_name: str) -> Tuple[bool, str]:
        # 限制：每天一次
        last = self._repo.get_last_move_at(user_id)
        now = int(time.time())
        if last and self._same_local_day(last, now):
            return False, "今天已经迁过城了，明天再来"

        # 校验目标城市存在且在四州
        c = self._city_by_name(target_city_name)
        if not c:
            return False, f"不存在的城市：{target_city_name}"
        if getattr(c, "province", None) not in ALLOWED_PROVINCES:
            return (
                False,
                f"只能迁到四州城市（益/扬/冀/兖），{target_city_name} 不在范围内",
            )

        # 设置基地并记录时间
        x, y = self._map.graph().positions.get(c.name, (0, 0))  # 获取坐标
        self._repo.set_base(user_id, c.name, int(x), int(y))
        self._repo.set_last_move_at(user_id, now)
        return True, f"迁城成功：{c.name}（{int(x)},{int(y)}）"
