# domain/services_resources.py
import time
from typing import Dict
from .entities import Player
from .ports import PlayerRepositoryPort
from .constants import (
    PRODUCTION_PER_MIN,
    CAPACITY_PER_LEVEL,
    BUILDING_TO_RESOURCE,
    BUILDING_ALIASES,
    RESOURCE_CN,
    MAX_LEVEL,
    MINUTE,
    UPGRADE_STONE_COST,
    UPGRADE_RESOURCE_COST,
)


def _fmt_cost(stone_cost: int, res_type: str, res_cost: int) -> str:
    res_cn = RESOURCE_CN[res_type]
    if res_type == "stone":
        # 两份石头合并展示更直观
        return f"石头 {stone_cost + res_cost}"
    return f"石头 {stone_cost}，{res_cn} {res_cost}"


class ResourceService:
    def __init__(self, repo: PlayerRepositoryPort):
        self._repo = repo
        self._repo.init_schema()

    # --- 基础 ---
    def _now(self) -> int:
        return int(time.time())

    def get_or_none(self, user_id: str):
        return self._repo.get_player(user_id)

    def register(self, user_id: str, nickname: str) -> Player:
        now = self._now()
        p = self._repo.get_player(user_id)
        if p:
            return p
        p = Player(
            user_id=user_id,
            nickname=nickname,
            created_at=now,
            last_tick=now,
            grain=0,
            gold=0,
            stone=0,
            troops=0,
            farm_level=1,
            bank_level=1,
            quarry_level=1,
            barracks_level=1,
        )
        self._repo.upsert_player(p)
        return p

    # --- 结算 ---
    # ---- 新：把等级全部夹紧到 [1, MAX_LEVEL]，并对 None/空串做兜底 ----
    @staticmethod
    def _san_level(x) -> int:
        try:
            v = int(x)
        except Exception:
            v = 1
        if v < 1:
            v = 1
        if v > MAX_LEVEL:
            v = MAX_LEVEL
        return v

    def _levels(self, p: Player) -> Dict[str, int]:
        return {
            "grain": self._san_level(getattr(p, "farm_level", 1)),
            "gold": self._san_level(getattr(p, "bank_level", 1)),
            "stone": self._san_level(getattr(p, "quarry_level", 1)),
            "troops": self._san_level(getattr(p, "barracks_level", 1)),
        }

    # ---- 新：容量封顶时不用 dict 直取，统一安全取值 ----
    def _apply_cap(self, res: Dict[str, int], lv: Dict[str, int]) -> Dict[str, int]:
        capped: Dict[str, int] = {}
        for r, v in res.items():
            r_id = r  # 这里资源键固定使用 'grain/gold/stone/troops'
            lv_idx = self._san_level(lv.get(r_id, 1))
            cap_list = CAPACITY_PER_LEVEL[r_id]
            cap = cap_list[lv_idx]
            capped[r_id] = v if v < cap else cap
        return capped

    # 其余不变；下面是 settle 里用安全等级取值的几行
    def settle(self, p: Player) -> Player:
        now = self._now()
        elapsed = max(0, now - (p.last_tick or 0))
        minutes = elapsed // MINUTE
        if minutes <= 0:
            return p

        lv = self._levels(p)
        gain = {
            "grain": PRODUCTION_PER_MIN["grain"][lv["grain"]] * minutes,
            "gold": PRODUCTION_PER_MIN["gold"][lv["gold"]] * minutes,
            "stone": PRODUCTION_PER_MIN["stone"][lv["stone"]] * minutes,
            "troops": PRODUCTION_PER_MIN["troops"][lv["troops"]] * minutes,
        }
        new_vals = {
            "grain": (p.grain or 0) + gain["grain"],
            "gold": (p.gold or 0) + gain["gold"],
            "stone": (p.stone or 0) + gain["stone"],
            "troops": (p.troops or 0) + gain["troops"],
        }
        new_vals = self._apply_cap(new_vals, lv)

        p.grain, p.gold, p.stone, p.troops = (
            new_vals["grain"],
            new_vals["gold"],
            new_vals["stone"],
            new_vals["troops"],
        )
        p.last_tick = now
        self._repo.upsert_player(p)
        return p

    # --- 查询 ---
    def status(self, p: Player) -> Dict[str, Dict[str, int]]:
        lv_res = {
            "grain": p.farm_level,
            "gold": p.bank_level,
            "stone": p.quarry_level,
            "troops": p.barracks_level,
        }
        lv_bld = {
            "farm": p.farm_level,
            "bank": p.bank_level,
            "quarry": p.quarry_level,
            "barracks": p.barracks_level,
        }
        caps = {r: CAPACITY_PER_LEVEL[r][lv_res[r]] for r in lv_res}
        prod = {r: PRODUCTION_PER_MIN[r][lv_res[r]] for r in lv_res}
        cur = {"grain": p.grain, "gold": p.gold, "stone": p.stone, "troops": p.troops}
        return {
            "level": lv_res,  # 资源键名
            "level_by_building": lv_bld,  # 建筑键名
            "cap": caps,
            "prod_per_min": prod,
            "cur": cur,
        }

    def upgrade(self, p: Player, building_name: str):
        """按固定表扣资源：需要 石头 + 建筑自身资源"""
        # 名称归一
        if building_name in BUILDING_ALIASES:
            bid = BUILDING_ALIASES[building_name]
        else:
            bid = building_name

        if bid not in BUILDING_TO_RESOURCE:
            return False, f"未知建筑：{building_name}", p

        # 懒结算，确保余额最新
        p = self.settle(p)

        # 当前等级与目标等级
        cur_lv = {
            "farm": p.farm_level,
            "bank": p.bank_level,
            "quarry": p.quarry_level,
            "barracks": p.barracks_level,
        }[bid]
        if cur_lv >= MAX_LEVEL:
            return False, f"{building_name} 已是满级 {MAX_LEVEL}", p
        target_lv = cur_lv + 1

        # 成本：石头 + 自身资源
        res_type = BUILDING_TO_RESOURCE[
            bid
        ]  # farm->grain, bank->gold, quarry->stone, barracks->troops
        stone_need = UPGRADE_STONE_COST[bid][target_lv]
        res_need = UPGRADE_RESOURCE_COST[res_type][target_lv]

        # 余额
        have = {"grain": p.grain, "gold": p.gold, "stone": p.stone, "troops": p.troops}

        # 校验余额
        stone_ok = have["stone"] >= (
            stone_need + (res_need if res_type == "stone" else 0)
        )
        res_ok = (
            (have[res_type] >= res_need) if res_type != "stone" else True
        )  # 若自身资源就是石头，上面合并校验了

        if not (stone_ok and res_ok):
            # 计算缺口
            lack_msgs = []
            if not stone_ok:
                need_total_stone = stone_need + (res_need if res_type == "stone" else 0)
                lack_msgs.append(f"石头 需要{need_total_stone}，当前{have['stone']}")
            if not res_ok:
                cn = RESOURCE_CN[res_type]
                lack_msgs.append(f"{cn} 需要{res_need}，当前{have[res_type]}")
            return False, "资源不足，升级失败：" + "；".join(lack_msgs), p

        # 扣款
        if res_type == "stone":
            # 两份石头一起扣
            p.stone -= stone_need + res_need
        else:
            p.stone -= stone_need
            if res_type == "grain":
                p.grain -= res_need
            elif res_type == "gold":
                p.gold -= res_need
            elif res_type == "troops":
                p.troops -= res_need

        # 升级
        new_lv = target_lv
        if bid == "farm":
            p.farm_level = new_lv
        elif bid == "bank":
            p.bank_level = new_lv
        elif bid == "quarry":
            p.quarry_level = new_lv
        else:
            p.barracks_level = new_lv

        self._repo.upsert_player(p)

        # 友好提示：本次花费 + 新等级
        msg_cost = _fmt_cost(stone_need, res_type, res_need)
        return True, f"{building_name} 升至 {new_lv} 级，花费：{msg_cost}", p
