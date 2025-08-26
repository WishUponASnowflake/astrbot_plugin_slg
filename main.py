# main.py
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .app.container import build_container
from .domain.constants import RESOURCE_CN, BUILDING_ALIASES, BUILDING_TO_RESOURCE

@register("astrbot_plugin_slg", "you", "SLG Map + Resource", "0.3.0", "repo_url")
class HexPipelinePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        self.container = build_container(context, config)
        self.map_svc = self.container.map_service
        self.state_svc = self.container.state_service
        self.pipe = self.container.pipeline
        self.hooks = self.container.hookbus
        self.res = self.container.res_service

    # 例子：
    # /slg 加入
    # /slg 资源
    # /slg 升级 农田
    @filter.command("slg")
    async def slg_entry(self, event: AstrMessageEvent, subcmd: str = None, arg1: str = None):
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid

        if not subcmd or subcmd.strip() in ["帮助", "help", "？", "?"]:
            yield event.plain_result("用法：/slg 加入 | 资源 | 升级 <农田/钱庄/采石场/军营> | 抽卡 <次数>")
            return

        subcmd = subcmd.strip()

        if subcmd == "加入":
            p = self.res.register(uid, name)
            yield event.plain_result(f"已加入。四建筑默认1级，开始自动产出。")
            return

        # 其他子命令需要已注册
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return

        if subcmd in ["资源", "状态"]:
            # 懒结算
            p = self.res.settle(p)
            s = self.res.status(p)
            lvb = s["level_by_building"]           # 这里用建筑键名
            prod = s["prod_per_min"]; cap = s["cap"]; cur = s["cur"]

            lines = [
                f"建筑等级：农田{lvb['farm']} 钱庄{lvb['bank']} 采石场{lvb['quarry']} 军营{lvb['barracks']}",
                f"产出/分钟：粮{prod['grain']} 金{prod['gold']} 石{prod['stone']} 兵{prod['troops']}",
                f"当前/上限：粮{cur['grain']}/{cap['grain']} 金{cur['gold']}/{cap['gold']} 石{cur['stone']}/{cap['stone']} 兵{cur['troops']}/{cap['troops']}",
            ]
            yield event.plain_result("\n".join(lines))
            return

        if subcmd == "升级":
            if not arg1:
                yield event.plain_result("用法：/slg 升级 <农田|钱庄|采石场|军营>")
                return
            ok, msg, p = self.res.upgrade(p, arg1.strip())
            if ok:
                # 升级后顺便结算一次让玩家看到新产能
                p = self.res.settle(p)
                s = self.res.status(p)
                prod = s["prod_per_min"]; lv = s["level"]
                yield event.plain_result(f"{msg}\n新产能/分钟：粮{prod['grain']} 金{prod['gold']} 石{prod['stone']} 兵{prod['troops']}")
            else:
                yield event.plain_result(msg)
            return

        if subcmd == "抽卡":
            # 次数
            try:
                times = int(arg1) if arg1 is not None else 1
            except:
                times = 1
            times = max(1, min(50, times))  # 别让你一口气 999
            got, spent, done = self.container.gacha_service.draw(p, times)

            # 全图鉴
            if done == 0 and len(got) == 0:
                yield event.plain_result("你已经集齐图鉴了，抽不出新角色。")
                return

            # 结果文本
            lines = []
            if done > 0:
                names = [f"{c.name}（{c.title}）" if c.title else c.name for c in got]
                lines.append(f"抽取成功 {done}/{times} 次")
                if names:
                    lines.append("获得：\n- " + "\n- ".join(names))
                # 消耗
                cost_str = []
                for k in ("gold","grain","stone","troops"):
                    if spent[k] > 0:
                        cn = {"gold":"金钱","grain":"粮食","stone":"石头","troops":"军队"}[k]
                        cost_str.append(f"{cn}{spent[k]}")
                if cost_str:
                    lines.append("总消耗：" + "，".join(cost_str))
            else:
                lines.append("资源不足，无法完成抽卡。")

            # 附加提示：下次单抽价格预览（不收费）
            nxt = p.draw_count + 1
            cst = self.container.gacha_service.cost_for_draw_index(nxt) if hasattr(self.container.gacha_service, "cost_for_draw_index") else None
            if cst:
                lines.append(f"下次单抽费用：金{cst['gold']} 粮{cst['grain']} 石{cst['stone']} 兵{cst['troops']}（前5次免费，6-15线性涨，之后恒定）")

            yield event.plain_result("\n".join(lines))
            return

        yield event.plain_result("未知子命令。用法：/slg 加入 | 资源 | 升级 <农田/钱庄/采石场/军营> | 抽卡 <次数>")

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
