# infra/assets.py
from __future__ import annotations
import base64
from pathlib import Path
from typing import Dict, Iterable, Optional

_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
}


def _to_data_uri(p: Path) -> Optional[str]:
    suf = p.suffix.lower()
    mime = _MIME.get(suf)
    if not mime or not p.exists():
        return None
    b = p.read_bytes()
    enc = base64.b64encode(b).decode("ascii")
    return f"data:{mime};base64,{enc}"


def _find_one(dir: Path, names: Iterable[str]) -> Optional[Path]:
    for n in names:
        p = dir / n
        if p.exists() and p.is_file():
            return p
    return None


def load_assets(picture_dir: Path, city_names: Iterable[str]) -> Dict:
    """从 picture/ 读取资源并转成 data URI"""
    picture_dir = picture_dir.resolve()
    assets = {"bg": None, "defaults": {}, "cities": {}}

    # 背景：bg.png 优先，其次 bg.jpg，或 background.*
    bgp = _find_one(
        picture_dir, ["bg.png", "bg.jpg", "background.png", "background.jpg"]
    )
    if bgp:
        assets["bg"] = _to_data_uri(bgp)

    # 类型兜底：优先 PNG，再 JPG
    def _pick(*candidates):
        p = _find_one(picture_dir, candidates)
        return _to_data_uri(p) if p else None

    assets["defaults"]["CITY"] = _pick("CITY.png", "CITY.jpg")
    assets["defaults"]["PASS"] = _pick("PASS.png", "PASS.jpg")
    assets["defaults"]["RESOURCE"] = _pick(
        "RESOURCE.png", "RESOURCE.jpg", "default.png", "default.jpg"
    )
    assets["defaults"]["DEFAULT"] = assets["defaults"]["RESOURCE"]

    # 城市专属：优先 PNG，再 JPG
    for name in city_names:
        cand = _find_one(picture_dir, [f"{name}.png", f"{name}.jpg"])
        if cand:
            assets["cities"][name] = _to_data_uri(cand)

    return assets
