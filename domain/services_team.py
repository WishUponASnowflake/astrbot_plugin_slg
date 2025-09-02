# domain/services_team.py
from __future__ import annotations
from typing import Dict, List, Tuple, Optional
from .ports import PlayerRepositoryPort
from .constants import (
    TEAM_COUNT,
    TEAM_SLOTS,
    TEAM_BASE_TROOPS,
    TROOPS_PER_LEVEL,
    CHAR_LEVEL_MAX,
    CHAR_LEVEL_UP_COST_RANGE,
)
from .entities import Player


def _linear_cost_at_level(target: int, mn: int, mx: int) -> int:
    """
    目标等级 target ∈ [2..CHAR_LEVEL_MAX] 的单次升级成本（线性）
    2 -> mn, 7 -> mx
    """
    lo, hi = 2, CHAR_LEVEL_MAX
    if target <= lo:
        return mn
    if target >= hi:
        return mx
    ratio = (target - lo) / (hi - lo)
    return int(round(mn + (mx - mn) * ratio))


class TeamService:
    def __init__(self, repo: PlayerRepositoryPort):
        self._repo = repo

    # ---- 读写编成 ----
    def ensure_teams(self, user_id: str):
        self._repo.ensure_teams(user_id, TEAM_COUNT, TEAM_SLOTS)

    def calc_capacity(self, user_id: str, team_no: int) -> int:
        slots = self._repo.list_team_slots(user_id, team_no)
        cap = TEAM_BASE_TROOPS
        for _, name in slots:
            if not name:
                continue
            lv = self._repo.get_char_level(user_id, name) or 1
            cap += lv * TROOPS_PER_LEVEL
        return cap

    def show_team(self, user_id: str, team_no: int) -> Dict:
        slots = self._repo.list_team_slots(user_id, team_no)
        soldiers = self._repo.get_team_soldiers(user_id, team_no)
        cap = self.calc_capacity(user_id, team_no)
        members = []
        for idx, name in slots:
            if name:
                lv = self._repo.get_char_level(user_id, name) or 1
                members.append({"slot": idx, "name": name, "level": lv})
            else:
                members.append({"slot": idx, "name": None, "level": None})
        return {
            "team_no": team_no,
            "soldiers": soldiers,
            "capacity": cap,
            "members": members,
        }

    def list_teams(self, user_id: str) -> List[Dict]:
        return [self.show_team(user_id, t) for t in range(1, TEAM_COUNT + 1)]

    def assign(
        self, user_id: str, char_name: str, team_no: int, slot_idx: Optional[int] = None
    ) -> Tuple[bool, str]:
        # 前置：拥有该角色
        if not self._repo.has_char(user_id, char_name):
            return False, f"没有角色：{char_name}"

        # 角色是否已在其他队伍
        pos = self._repo.find_char_team(user_id, char_name)
        if pos is not None:
            old_team, old_slot = pos
            if old_team == team_no and (slot_idx is None or slot_idx == old_slot):
                return True, f"{char_name} 已在队伍{team_no}的槽位{old_slot}"
            # 先从旧位移除
            self._repo.set_team_slot(user_id, old_team, old_slot, None)

        # 若未指定槽位，找第一个空位
        slots = self._repo.list_team_slots(user_id, team_no)
        if slot_idx is None:
            empty = next((i for i, name in slots if not name), None)
            if empty is None:
                return False, f"队伍{team_no}已满"
            slot_idx = empty
        else:
            if slot_idx < 1 or slot_idx > TEAM_SLOTS:
                return False, f"槽位必须 1~{TEAM_SLOTS}"
            # 如果该位已有别的角色，先挤掉
            self._repo.set_team_slot(user_id, team_no, slot_idx, None)

        self._repo.set_team_slot(user_id, team_no, slot_idx, char_name)

        # 角色编入后可能提升容量，不自动补兵
        # 若兵力超过新容量（几乎不可能），则下修
        cap = self.calc_capacity(user_id, team_no)
        cur = self._repo.get_team_soldiers(user_id, team_no)
        if cur > cap:
            self._repo.set_team_soldiers(user_id, team_no, cap)
        return True, f"{char_name} 已加入队伍{team_no} 槽位{slot_idx}"

    # ---- 补兵：把队伍兵力拉到上限，消耗玩家 troops ----
    def reinforce(self, p: Player, team_no: int) -> Tuple[bool, str, Player]:
        self.ensure_teams(p.user_id)
        cap = self.calc_capacity(p.user_id, team_no)
        cur = self._repo.get_team_soldiers(p.user_id, team_no)
        need = max(0, cap - cur)
        if need == 0:
            return True, f"队伍{team_no} 已满编（{cur}/{cap}）", p
        if p.troops <= 0:
            return False, f"兵力不足，当前士兵 {p.troops}，需要 {need}", p
        add = min(need, p.troops)
        p.troops -= add
        self._repo.set_team_soldiers(p.user_id, team_no, cur + add)
        self._repo.upsert_player(p)
        return True, f"队伍{team_no} 补兵 +{add}（{cur + add}/{cap}）", p

    # ---- 角色升级：扣资源，+1 级 ----
    def upgrade_char(self, p: Player, char_name: str) -> Tuple[bool, str, Player]:
        if not self._repo.has_char(p.user_id, char_name):
            return False, f"没有角色：{char_name}", p
        lv = self._repo.get_char_level(p.user_id, char_name) or 1
        if lv >= CHAR_LEVEL_MAX:
            return False, f"{char_name} 已达上限 {CHAR_LEVEL_MAX} 级", p

        target = lv + 1
        cost = {
            r: _linear_cost_at_level(target, *CHAR_LEVEL_UP_COST_RANGE[r])
            for r in CHAR_LEVEL_UP_COST_RANGE
        }

        # 余额检查
        if (
            p.gold < cost["gold"]
            or p.grain < cost["grain"]
            or p.stone < cost["stone"]
            or p.troops < cost["troops"]
        ):
            return (
                False,
                (
                    f"资源不足：需 金{cost['gold']} 粮{cost['grain']} 石{cost['stone']} 兵{cost['troops']}，"
                    f"当前 金{p.gold} 粮{p.grain} 石{p.stone} 兵{p.troops}"
                ),
                p,
            )

        # 扣费
        p.gold -= cost["gold"]
        p.grain -= cost["grain"]
        p.stone -= cost["stone"]
        p.troops -= cost["troops"]

        # 升级
        self._repo.set_char_level(p.user_id, char_name, target)
        self._repo.upsert_player(p)

        # 如果该角色在某队伍，容量可能上升，但不自动补兵
        return (
            True,
            f"{char_name} 升至 {target} 级，花费：金{cost['gold']} 粮{cost['grain']} 石{cost['stone']} 兵{cost['troops']}",
            p,
        )
