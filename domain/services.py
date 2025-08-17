# domain/services.py
from typing import Dict, List, Tuple, Optional
from .ports import MapProviderPort, StateRepositoryPort
from .entities import City, MapGraph, Gate, MILESTONES

class MapService:
    def __init__(self, provider: MapProviderPort):
        self._graph: MapGraph = provider.load()

    # -- 基础 --
    def list_provinces(self) -> List[str]:
        ps = sorted({c.province for c in self._graph.cities.values()})
        return ps

    def list_cities(self) -> List[str]:
        return sorted(self._graph.cities.keys())

    def get_city(self, name: str) -> Optional[City]:
        return self._graph.cities.get(name)

    def list_cities_by_province(self, p: str) -> List[str]:
        return sorted([c.name for c in self._graph.cities.values() if c.province == p])

    # -- 战线/邻居 --
    def gates(self, city: str) -> List[Gate]:
        return list(self._graph.lines.get(city, {}).keys())

    def neighbor(self, city: str, gate: Gate) -> Optional[str]:
        return self._graph.lines.get(city, {}).get(gate)

    def frontlines(self, city: str) -> Dict[Gate, str]:
        return self._graph.lines.get(city, {}).copy()

    # -- HTML 渲染数据需要 --
    def graph(self) -> MapGraph:
        return self._graph

class StateService:
    def __init__(self, repo: StateRepositoryPort):
        self._repo = repo
        self._repo.init_schema()

    # KV 通用
    def get(self, key: str):
        return self._repo.get(key)

    def set(self, key: str, val: str):
        self._repo.set(key, val)

    # 战线进度：里程碑索引(0..2)与当前百分比(0..100)
    def get_line_progress(self, city: str, gate: Gate) -> Tuple[int, int]:
        idx = self._repo.get(f"line:{city}:{gate}:milestone")
        prog = self._repo.get(f"line:{city}:{gate}:progress")
        try:
            mi = int(idx) if idx is not None else 0
        except Exception:
            mi = 0
        try:
            pr = int(prog) if prog is not None else 0
        except Exception:
            pr = 0
        mi = max(0, min(mi, len(MILESTONES)-1))
        pr = max(0, min(pr, 100))
        return mi, pr

    def set_line_progress(self, city: str, gate: Gate, milestone_idx: int, progress: int):
        milestone_idx = max(0, min(milestone_idx, len(MILESTONES)-1))
        progress = max(0, min(progress, 100))
        self._repo.set(f"line:{city}:{gate}:milestone", str(milestone_idx))
        self._repo.set(f"line:{city}:{gate}:progress", str(progress))

    def push_progress(self, city: str, gate: Gate, delta: int = 0):
        mi, pr = self.get_line_progress(city, gate)
        pr += delta
        while pr >= 100 and mi < len(MILESTONES)-1:
            pr -= 100
            mi += 1
        pr = min(pr, 100)
        self.set_line_progress(city, gate, mi, pr)
