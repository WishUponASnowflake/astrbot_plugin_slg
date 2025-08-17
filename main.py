# main.py
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .app.container import build_container

@register("astrbot_plugin_slg", "you", "SLG Map with Hex+Pipeline+Hooks+SQLite", "0.2.0", "repo_url")
class HexPipelinePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.container = build_container(context, config)
        self.map_svc = self.container.map_service
        self.state_svc = self.container.state_service
        self.pipe = self.container.pipeline
        self.hooks = self.container.hookbus

    # ====== 地图命令 ======

    @filter.command("slg_map")
    async def show_big_map(self, event: AstrMessageEvent):
        """渲染大地图为图片并发送（最小参数集）"""
        # 还是用你现成的 HTML（含 SVG、样式、说明文字）
        html = self.container.build_map_html()

        try:
            # 关键点：只传 tmpl + data，别给 options 添乱
            url = await self.html_render(
                tmpl=html,
                data={},         # 目前没用到变量，留空即可
                # 不传 options，走默认。默认一般是 png 且不会带 quality
                # return_url 默认 True，拿到 URL
            )
            # 用“图片结果”接口交给平台自己发
            yield event.image_result(url)
        except Exception as e:
            # 若服务端继续回 text/plain 的错误文本，这里能把原始信息吐出来
            yield event.plain_result(f"HTML渲染失败：{e}")



    @filter.command("slg_map_url")
    async def show_big_map_url(self, event: AstrMessageEvent):
        html = self.container.build_map_html()
        img_url = await self.html_render(tmpl=html, data={}, return_url=True, options={"type": "png", "full_page": True})
        yield event.plain_result(f"渲染URL：{img_url}")

    @filter.command("line")
    async def show_city_lines(self, event: AstrMessageEvent, city: str):
        """查看某城的战线与里程碑"""
        c = self.map_svc.get_city(city)
        if not c:
            yield event.plain_result(f"未找到城市：{city}")
            return
        fl = self.map_svc.frontlines(city)
        if not fl:
            yield event.plain_result(f"{city} 暂无对外战线")
            return
        parts = []
        for gate, nb in fl.items():
            mi, pr = self.state_svc.get_line_progress(city, gate)
            parts.append(f"{gate} → {nb} | 里程碑：{mi+1}/3（{['前沿','箭楼','外城门'][mi]}）| 进度：{pr}%")
        yield event.plain_result(f"{city}（{c.province}州{'·州府' if c.capital else ''}）：\n" + "\n".join(parts))

    @filter.command("line_push")
    async def push_line(self, event: AstrMessageEvent, city: str, gate: str, delta: int):
        """占位推进：为某城某门推进 delta%（0-100）"""
        if gate not in ("北门","东门","西门","南门","西北门"):  # 简易容错
            yield event.plain_result(f"门名不合法：{gate}")
            return
        if not self.map_svc.get_city(city):
            yield event.plain_result(f"未找到城市：{city}")
            return
        nb = self.map_svc.neighbor(city, gate)  # 可能为 None
        if not nb:
            yield event.plain_result(f"{city} 的 {gate} 没有战线")
            return
        self.state_svc.push_progress(city, gate, max(0, min(100, int(delta))))
        mi, pr = self.state_svc.get_line_progress(city, gate)
        yield event.plain_result(f"已推进 {city} {gate} → {nb}，现在：{['前沿','箭楼','外城门'][mi]} {pr}%")

    # ====== 你之前的示例命令保留也行（map、neighbor、path、state_*） ======

    @filter.command("map")
    async def map_root(self, event: AstrMessageEvent):
        nodes = self.map_svc.list_cities()
        yield event.plain_result("城市: " + ", ".join(nodes))

    @filter.command("neighbor")
    async def map_neighbor(self, event: AstrMessageEvent, node: str):
        fl = self.map_svc.frontlines(node)
        if not fl:
            yield event.plain_result(f"{node} 无战线")
            return
        pairs = [f"{g}→{nb}" for g, nb in fl.items()]
        yield event.plain_result(f"{node} 战线: " + " | ".join(pairs))
