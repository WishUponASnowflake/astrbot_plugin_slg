# app/container.py
from pathlib import Path
from typing import Any

from ..domain.services import MapService, StateService
from ..infra.sqlite_repo import SQLiteStateRepository
from ..infra.map_provider import StaticMapProvider
from ..infra.hooks import HookBus
from ..app_pipeline.pipeline import Pipeline
from ..app_pipeline.stages import NormalizeStage, AuditStage
from ..infra.html_renderer import build_map_html
from ..infra.assets import load_assets  # <- 新增

class Container:
    def __init__(self, map_service, state_service, pipeline, hookbus, assets):
        self.map_service = map_service
        self.state_service = state_service
        self.pipeline = pipeline
        self.hookbus = hookbus
        self.assets = assets

    def close(self):
        # repo 在 StateService 内部持有连接，简单起见这里不重复关
        pass

def _resolve_data_dir(context, config) -> Path:
    try:
        base = Path(getattr(context, "data_dir", "data")).resolve()
    except Exception:
        base = Path("data").resolve()
    rel = (config or {}).get("db_relative_dir") or "plugin_data/astrbot_plugin_hexpipeline"
    target = base / rel
    target.mkdir(parents=True, exist_ok=True)
    return target

def _resolve_picture_dir() -> Path:
    # 不用所谓“plugin root 变量”，就从文件相对位置找 picture/
    # app/container.py -> 插件根目录 -> picture/
    return Path(__file__).resolve().parents[1] / "picture"

def build_container(context, config=None) -> Container:
    data_dir = _resolve_data_dir(context, config)

    repo = SQLiteStateRepository(db_path=data_dir / "state.sqlite3")
    map_provider = StaticMapProvider()

    map_service = MapService(map_provider)
    state_service = StateService(repo)

    pipeline = Pipeline(stages=[NormalizeStage(), AuditStage()])
    hookbus = HookBus()

    # 预载图片资源为 data URI
    picture_dir = _resolve_picture_dir()
    city_names = map_service.list_cities()
    assets = load_assets(picture_dir, city_names)

    c = Container(map_service=map_service, state_service=state_service, pipeline=pipeline, hookbus=hookbus, assets=assets)
    # 生成 HTML 时把 assets 一并传入
    c.build_map_html = lambda: build_map_html(map_service.graph(), state_service.get_line_progress, assets)
    return c
