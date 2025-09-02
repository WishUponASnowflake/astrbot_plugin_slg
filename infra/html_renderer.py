# infra/html_renderer.py
from typing import Dict, Tuple, Optional
from ..domain.entities import MapGraph, MILESTONES, City

# ===== 画布与样式 =====
CANVAS_W, CANVAS_H = 800, 620
ICON_SIZE_NORMAL = 38  # 放大
ICON_SIZE_CAPITAL = 48
ICON_SIZE_PASS = 80  # ← 新增：关隘（PASS）大小，随你改
FONT_SIZE = 15
LABEL_OFFSET = 16
SHOW_PROVINCE_LABELS = True

LINE_STROKE = "rgba(55,65,81,0.70)"  # 浅色线路
ARROW_FILL = "rgba(55,65,81,0.70)"
PROG_ON = "#58d17a"
PROG_OFF = "#d1d5db"

PROVINCE_LABEL_POS: Dict[str, Tuple[int, int]] = {
    "雍": (120, 240),
    "豫": (290, 285),
    "冀": (380, 150),
    "兖": (435, 225),
    "青": (535, 165),
    "徐": (515, 295),
    "扬": (610, 370),
    "荆": (235, 375),
    "益": (140, 485),
}

LABEL_ANCHOR: Dict[str, str] = {
    "长安": "E",
    "潼关": "N",
    "洛阳": "N",
    "许昌": "E",
    "陈留": "N",
    "汝南": "E",
    "邺": "N",
    "南皮": "S",
    "鄄城": "S",
    "东阿": "N",
    "临淄": "S",
    "北海": "S",
    "彭城": "S",
    "下邳": "E",
    "建业": "W",
    "会稽": "W",
    "襄阳": "E",
    "江陵": "E",
    "汉中": "W",
    "成都": "N",
    "江州": "N",
}


def _city_title(c: City) -> str:
    kind = (
        "州府"
        if c.capital
        else (
            "城市" if c.ntype == "CITY" else ("关隘" if c.ntype == "PASS" else "资源镇")
        )
    )
    return f"{c.name}（{c.province}州，{kind}）"


def _pick_icon(city: City, assets: Dict) -> Optional[str]:
    if assets.get("cities", {}).get(city.name):
        return assets["cities"][city.name]
    if city.ntype == "PASS" and assets.get("defaults", {}).get("PASS"):
        return assets["defaults"]["PASS"]
    if city.ntype == "CITY" and assets.get("defaults", {}).get("CITY"):
        return assets["defaults"]["CITY"]
    if city.ntype == "RESOURCE" and assets.get("defaults", {}).get("RESOURCE"):
        return assets["defaults"]["RESOURCE"]
    return assets.get("defaults", {}).get("DEFAULT")


def _label_attrs(x: int, y: int, anchor: str):
    if anchor == "W":
        return x - LABEL_OFFSET, y + 5, "end", 0
    if anchor == "N":
        return x, y - (LABEL_OFFSET + 2), "middle", 0
    if anchor == "S":
        return x, y + (LABEL_OFFSET + FONT_SIZE - 6), "middle", 0
    return x + LABEL_OFFSET, y + 5, "start", 0


def build_map_html(graph: MapGraph, get_progress, assets: Dict):
    layers_bg = []
    layers_edges = []
    layers_nodes = []  # 节点与文字最后渲染，确保最上层

    # 背景
    if assets.get("bg"):
        layers_bg.append(
            f'<image href="{assets["bg"]}" x="0" y="0" width="{CANVAS_W}" height="{CANVAS_H}" '
            'preserveAspectRatio="xMidYMid slice" opacity="0.85"></image>'
        )
    else:
        layers_bg.append(
            f'<rect x="0" y="0" width="{CANVAS_W}" height="{CANVAS_H}" fill="#f7f7f3"></rect>'
        )

    # 省名标签（可关）
    if SHOW_PROVINCE_LABELS:
        for p, (px, py) in PROVINCE_LABEL_POS.items():
            layers_bg.append(
                f'<text x="{px}" y="{py}" font-size="{FONT_SIZE}" fill="rgba(0,0,0,0.55)" font-weight="600">{p}州</text>'
            )

    # 线路与进度条：用 graph.positions
    POS = graph.positions
    for city, gates in graph.lines.items():
        if city not in POS:
            continue
        x1, y1 = POS[city]
        for gate, nb in gates.items():
            if nb not in POS:
                continue
            x2, y2 = POS[nb]
            layers_edges.append(
                f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" '
                f'stroke="{LINE_STROKE}" stroke-width="3" stroke-linecap="round" marker-end="url(#arrow)"></line>'
            )
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2 - 6
            mi, pr = get_progress(city, gate)
            seg_w, gap, h = 12, 2, 7
            start_x = mx - (3 * seg_w + 2 * gap) // 2
            for i in range(3):
                active = (i < mi) or (i == mi and pr >= 100)
                fill = PROG_ON if active else PROG_OFF
                w = seg_w if i < mi else (int(seg_w * pr / 100) if i == mi else seg_w)
                layers_edges.append(
                    f'<rect x="{start_x + i * (seg_w + gap)}" y="{my - h // 2}" width="{w}" height="{h}" rx="2" '
                    f'fill="{fill}" stroke="#374151" stroke-width="0.6" />'
                )

    # 城市图标与文字：同样用 POS
    for name, city in graph.cities.items():
        if name not in POS:
            continue
        x, y = POS[name]
        icon = _pick_icon(city, assets)
        size = (
            ICON_SIZE_CAPITAL
            if city.capital
            else (ICON_SIZE_PASS if city.ntype == "PASS" else ICON_SIZE_NORMAL)
        )
        half = size // 2

        if icon:
            layers_nodes.append(
                f'<image href="{icon}" x="{x - half}" y="{y - half}" width="{size}" height="{size}" '
                'clip-path="inset(0 round 8)" filter="url(#nodeGlow)"></image>'
            )
        else:
            # 极少走到：没有图标就放一个小方块，也不画圆
            layers_nodes.append(
                f'<rect x="{x - half}" y="{y - half}" width="{size}" height="{size}" rx="8" ry="8" '
                'fill="#ffffff" stroke="#111827" stroke-width="1.2" filter="url(#nodeGlow)"></rect>'
            )

        lx, ly, anchor, _ = _label_attrs(x, y, LABEL_ANCHOR.get(name, "E"))
        layers_nodes.append(
            f'<text x="{lx}" y="{ly}" text-anchor="{anchor}" font-size="{FONT_SIZE}" '
            'fill="#111827" font-weight="700" paint-order="stroke fill" '
            'stroke="rgba(255,255,255,0.95)" stroke-width="3">'
            f"{name}</text>"
        )

        flines = graph.lines.get(name, {})
        tips = []
        for g, nb in flines.items():
            mi, pr = get_progress(name, g)
            tips.append(f"{g}→{nb}：{MILESTONES[mi]} {pr}%")
        tip = _city_title(city) + ("\\n" + "\\n".join(tips) if tips else "")
        layers_nodes.append(f"<title>{tip}</title>")

    html = f"""<!doctype html>
<meta charset="utf-8" />
<div style="font-family: -apple-system,Segoe UI,Roboto,Helvetica,Arial;">
  <svg width="100%" viewBox="0 0 {CANVAS_W} {CANVAS_H}">
    <defs>
      <marker id="arrow" markerWidth="12" markerHeight="10" refX="11" refY="5" orient="auto">
        <path d="M0,0 L12,5 L0,10 z" fill="{ARROW_FILL}"></path>
      </marker>
      <!-- 柔和高亮，不是画圆，而是给图标加白色内发光 -->
      <filter id="nodeGlow" x="-50%" y="-50%" width="200%" height="200%">
        <feDropShadow dx="0" dy="0" stdDeviation="2.3" flood-color="#ffffff" flood-opacity="0.95"/>
      </filter>
    </defs>
    <g id="bg">{"".join(layers_bg)}</g>
    <g id="edges">{"".join(layers_edges)}</g>
    <g id="nodes">{"".join(layers_nodes)}</g>
  </svg>
</div>"""
    return html
