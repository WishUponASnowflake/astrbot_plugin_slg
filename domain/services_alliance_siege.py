# domain/services_alliance_siege.py
from __future__ import annotations
import time, collections, math
from typing import List, Dict, Tuple, Optional
from .constants import SIEGE_WINDOW_MINUTES, SIEGE_EDGE_MINUTES, SIEGE_CITY_REQUIRE
from .ports import PlayerRepositoryPort

class AllianceSiegeService:
    """
    依赖：
      - repo: PlayerRepositoryPort + 上面新加的攻城方法
      - map_service: 需要 graph()，且图有城市与邻接；优先使用 g.neighbors(name)。
      - 读队伍：repo.list_team_slots(uid, team_no) + repo.get_char_level(uid, name)
    """
    def __init__(self, repo: PlayerRepositoryPort, map_service):
        self._repo = repo
        self._map  = map_service

    # -------- 图相关 --------
    def _neighbors(self, city: str) -> List[str]:
        g = self._map.graph()
        if hasattr(g, "neighbors"):
            return list(g.neighbors(city))
        # 兜底：常见字段推断
        if hasattr(g, "adj") and isinstance(g.adj, dict):
            return list(g.adj.get(city, []))
        if hasattr(g, "roads") and isinstance(g.roads, dict):
            return list(g.roads.get(city, []))
        if hasattr(g, "edges") and isinstance(g.edges, dict):
            neigh=set()
            for a, bs in g.edges.items():
                if a == city: neigh.update(bs)
                if isinstance(bs, (list, set)) and city in bs: neigh.add(a)
            return list(neigh)
        if hasattr(g, "lines") and isinstance(g.lines, dict):
            # 处理 MapGraph 的 lines 结构：{city: {gate: target_city}}
            neigh = set()
            if city in g.lines:
                # 直接获取该城市的所有连接目标
                city_lines = g.lines[city]
                if isinstance(city_lines, dict):
                    for gate, target_city in city_lines.items():
                        if target_city and target_city != city:
                            neigh.add(target_city)
            return list(neigh)
        return []

    def _shortest_path(self, src: str, dst: str) -> List[str]:
        if src == dst: return [src]
        q = collections.deque([src])
        prev = {src: None}
        while q:
            u = q.popleft()
            for v in self._neighbors(u):
                if v in prev: continue
                prev[v] = u
                if v == dst:
                    # 回溯
                    path=[v]
                    while u is not None:
                        path.append(u); u = prev[u]
                    path.reverse()
                    return path
                q.append(v)
        return []  # 不连通

    # -------- 城市信息 --------
    def _city_obj(self, name: str):
        return self._map.graph().cities.get(name)

    def _city_level(self, name: str) -> int:
        c = self._city_obj(name)
        lv = getattr(c, "level", None)
        try:
            lv = int(lv) if lv is not None else 1
        except Exception:
            lv = 1
        return max(1, min(4, lv))

    # -------- 参战产出 --------
    def _team1_level_sum(self, uid: str) -> int:
        slots = self._repo.list_team_slots(uid, 1)
        s = 0
        for _, name in slots:
            if not name: continue
            lv = self._repo.get_char_level(uid, name) or 1
            s += lv
        return s

    # -------- 发起/集结/状态 --------
    def schedule_siege(self, leader_uid: str, city: str, start_at: int) -> Tuple[bool, str]:
        # 必须在同盟中，且是领袖
        a = self._repo.get_user_alliance(leader_uid)
        if not a: return False, "你未加入任何同盟"
        if a.get("leader_user_id") != leader_uid: return False, "仅同盟领袖可发起攻城"
        # 城市存在
        if not self._city_obj(city): return False, f"不存在的城市：{city}"
        # 不允许重复活动
        act = self._repo.get_active_siege_by_alliance(a["id"])
        if act: return False, "已有进行中的攻城或未开始的计划"
        lv = self._city_level(city)
        sid = self._repo.create_siege(a["id"], city, lv, start_at, leader_uid)
        return True, f"已创建攻城计划#{sid}：{city} 等级{lv} 开战时间 {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(start_at))}"

    def join_rally(self, uid: str) -> Tuple[bool, str]:
        a = self._repo.get_user_alliance(uid)
        if not a: return False, "你未加入任何同盟"
        act = self._repo.get_active_siege_by_alliance(a["id"])
        if not act: return False, "当前同盟没有攻城计划"
        # 取玩家当前城市（用基地城市）
        base = self._repo.get_base(uid)
        if not base or not base.get("city"):
            return False, "你还没有基地城市，先用 slg 基地 初始化"
        src = base["city"]; dst = act["city"]

        path = self._shortest_path(src, dst)
        if not path: return False, f"从 {src} 到 {dst} 没有连通路径"

        hops = max(0, len(path)-1)
        eta  = int(time.time()) + hops * SIEGE_EDGE_MINUTES * 60
        self._repo.add_siege_participant(act["id"], uid, src, path, hops, eta)
        return True, f"已集结：#{act['id']} {src} -> {dst}，{hops} 段，预计 {time.strftime('%H:%M', time.localtime(eta))} 到达"

    def status_and_maybe_finalize(self, uid: str) -> Tuple[bool, str]:
        a = self._repo.get_user_alliance(uid)
        if not a: return False, "你未加入任何同盟"
        act = self._repo.get_active_siege_by_alliance(a["id"])
        if not act: return False, "当前没有攻城活动"
        now = int(time.time())
        start_at = int(act["start_at"])
        end_at   = start_at + SIEGE_WINDOW_MINUTES * 60

        # 自动状态推进
        if now >= start_at and act["state"] == "scheduled":
            self._repo.update_siege_state(act["id"], "ongoing", None)
            act["state"] = "ongoing"
        if now < start_at:
            # 未开始，仅展示队列
            parts = self._repo.list_siege_participants(act["id"])
            lines = [f"攻城计划#{act['id']} 目标：{act['city']} 等级{act['city_level']} 开战：{time.strftime('%Y-%m-%d %H:%M', time.localtime(start_at))}"]
            for p in parts:
                lines.append(f"- {p['user_id']} 从{p['from_city']} 集结路径{len(p['path'])-1}段 预计{time.strftime('%H:%M', time.localtime(p['eta']))}到")
            return True, "\n".join(lines)

        # 进行中或已到期：累计贡献
        parts = self._repo.list_siege_participants(act["id"])
        total_pts = 0
        det_lines = []
        for p in parts:
            # 到达时间与可贡献时长
            arrive = max(p["eta"], start_at)  # 迟到者从到达时刻开始贡献
            if now <= arrive:
                contrib_min = 0
            else:
                # 截断到攻城窗口内
                t_end = min(now, end_at)
                contrib_min = max(0, int((t_end - arrive) // 60))
            # 产出/分钟 = 队伍1等级和
            lv_sum = self._team1_level_sum(p["user_id"])
            pts = lv_sum * contrib_min
            total_pts += pts
            det_lines.append(f"- {p['user_id']} 等级和{lv_sum} 贡献{contrib_min}分钟 -> {pts}点")

        need = SIEGE_CITY_REQUIRE.get(int(act["city_level"]), 1200)
        header = [f"攻城#{act['id']} 目标：{act['city']} Lv{act['city_level']} 进度：{total_pts}/{need}",
                  f"窗口：{time.strftime('%H:%M', time.localtime(start_at))} - {time.strftime('%H:%M', time.localtime(end_at))} 当前：{time.strftime('%H:%M', time.localtime(now))}"]
        # 若到期则结算
        if now >= end_at and act["state"] in ("scheduled","ongoing"):
            result = "success" if total_pts >= need else "fail"
            self._repo.update_siege_state(act["id"], "done", result)
            suffix = "【攻城成功】" if result == "success" else "【攻城失败】"
            header.append(suffix)
        return True, "\n".join(header + det_lines)
