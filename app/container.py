# app/container.py
from pathlib import Path
from typing import Any
from inspect import signature

from ..domain.services import MapService, StateService
from ..infra.sqlite_repo import SQLiteStateRepository
from ..infra.map_json_provider import JsonMapProvider
from ..app_pipeline.pipeline import Pipeline
from ..app_pipeline.stages import NormalizeStage, AuditStage
from ..infra.hooks import HookBus
from ..infra.assets import load_assets
from ..infra.html_renderer import build_map_html
from ..infra.sqlite_player_repo import SQLitePlayerRepository
from ..infra.character_provider import CharacterProvider
from ..domain.services_gacha import GachaService
from ..domain import services_resources as _res_mod
ResourceService = _res_mod.ResourceService
print(f"[SLG] ResourceService origin: {_res_mod.__file__}")

from ..domain.services_team import TeamService # 新增

PLUGIN_NS = "astrbot_plugin_slg"

class Container:
    def __init__(self, map_service, state_service, pipeline, hookbus, assets, res_service, gacha_service, team_service): # 修改
        self.map_service = map_service
        self.state_service = state_service
        self.pipeline = pipeline
        self.hookbus = hookbus
        self.assets = assets
        self.res_service = res_service
        self.gacha_service = gacha_service
        self.team_service = team_service # 新增
        self.build_map_html = None

def _data_root(context) -> Path:
    # 不用 resolve，遵循 AstrBot 相对 data/ 的做法
    base = Path(getattr(context, "data_dir", "data"))
    root = base / "plugin_data" / PLUGIN_NS
    root.mkdir(parents=True, exist_ok=True)
    _maybe_migrate_old(base, root)  # 可选：把你之前的 db 挪过来
    return root

def _maybe_migrate_old(base: Path, new_root: Path):
    # 之前我们用过 data/plugins/astrbot_plugin_slg，这里顺手迁一次
    old = base / "plugins" / PLUGIN_NS
    if not old.exists():
        return
    for fname in ("players.sqlite3", "state.sqlite3"):
        src = old / fname
        dst = new_root / fname
        try:
            if src.exists() and not dst.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                src.replace(dst)  # 同盘原子移动
                print(f"[SLG] migrated {src} -> {dst}")
        except Exception as e:
            print(f"[SLG] migrate {src} failed: {e}")

def _resolve_map_json() -> Path:
    # 插件根/map/three_kingdoms.json（不玩什么“root 变量”，用相对本文件）
    return Path(__file__).resolve().parents[1] / "map" / "three_kingdoms.json"

def _resolve_char_json() -> Path:
    return Path(__file__).resolve().parents[1] / "characters" / "character.json"

def _resolve_picture_dir() -> Path:
    # 不用所谓“plugin root 变量”，就从文件相对位置找 picture/
    # app/container.py -> 插件根目录 -> picture/
    return Path(__file__).resolve().parents[1] / "picture"

def build_container(context, config=None) -> Container:
    data_root = _data_root(context)

    # 固定落在 data/plugin_data/astrbot_plugin_slg
    player_repo = SQLitePlayerRepository(db_path=data_root / "players.sqlite3")
    res_service = ResourceService(player_repo)
    team_service = TeamService(player_repo) # 新增

    state_repo = SQLiteStateRepository(db_path=data_root / "state.sqlite3")
    map_provider = JsonMapProvider(_resolve_map_json())
    map_service = MapService(map_provider)
    state_service = StateService(state_repo)

    pipeline = Pipeline(stages=[NormalizeStage(), AuditStage()])
    hookbus = HookBus()

    picture_dir = _resolve_picture_dir()
    assets = load_assets(picture_dir, map_service.list_cities())

    # 角色池
    pool = CharacterProvider(_resolve_char_json()).load_all()
    gacha = GachaService(player_repo, res_service, pool)

    c = Container(map_service, state_service, pipeline, hookbus, assets, res_service, gacha, team_service) # 修改
    c.build_map_html = lambda: build_map_html(map_service.graph(), state_service.get_line_progress, assets)
    print(f"[SLG] data_root = {data_root}")
    return c
