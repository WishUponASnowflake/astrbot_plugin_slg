from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Tuple
from ..domain.entities import MapGraph, City

class JsonMapProvider:
    def __init__(self, json_path: Path):
        self._json_path = Path(json_path)

    def load(self) -> MapGraph:
        data = json.loads(self._json_path.read_text(encoding="utf-8"))
        raw_cities: Dict[str, dict] = data["cities"]

        cities: Dict[str, City] = {}
        lines: Dict[str, Dict[str, str]] = {}
        positions: Dict[str, Tuple[int, int]] = {}

        # 一次遍历装配
        for name, cfg in raw_cities.items():
            c = City(
                name=name,
                province=cfg["province"],
                ntype=cfg.get("type", "CITY"),
                capital=bool(cfg.get("capital", False)),
            )
            cities[name] = c
            positions[name] = tuple(cfg["pos"])  # (x, y)
            lines[name] = dict(cfg.get("lines", {}))

        # 可选校验：战线指向的城市必须存在
        for src, gs in list(lines.items()):
            for gate, dst in list(gs.items()):
                if dst not in cities:
                    raise ValueError(f"线路非法：{src} 的 {gate} 指向未知城市 {dst}")

        return MapGraph(cities=cities, lines=lines, positions=positions)
