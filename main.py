# main.py
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register

from .app.container import build_container
from .domain.constants import RESOURCE_CN, BUILDING_ALIASES, BUILDING_TO_RESOURCE, DrawResultStatus

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

    # SLG 主命令组
    @filter.command_group("slg")
    def slg_group(self):
        pass

    @slg_group.command("加入", alias={"join"})
    async def slg_join(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.register(uid, name)
        yield event.plain_result(f"已加入。四建筑默认1级，开始自动产出。")

    @slg_group.command("帮助", alias={"help", "？", "?"})
    async def slg_help(self, event: AstrMessageEvent):
        yield event.plain_result("用法：/slg 加入 | 资源 | 升级 <农田/钱庄/采石场/军营> | 抽卡 <次数>")

    @slg_group.command("进军", alias={"攻打", "开战"})
    async def slg_march(self, event: AstrMessageEvent, target: str):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        if not target.isdigit():
            yield event.plain_result("用法：slg 进军 对方ID（数字）")
            return
        defender_uid = target

        p_me = self.container.res_service.get_or_none(uid)
        if not p_me:
            yield event.plain_result("你还没加入游戏，先执行：slg 加入"); return
        p_enemy = self.container.res_service.get_or_none(defender_uid)
        if not p_enemy:
            yield event.plain_result("对方未加入游戏"); return

        # 保证队伍表存在
        self.container.team_service.ensure_teams(uid)
        self.container.team_service.ensure_teams(defender_uid)

        a_slots = self.container.res_service._repo.list_team_slots(uid, 1)
        b_slots = self.container.res_service._repo.list_team_slots(defender_uid, 1)
        if not any(n for _, n in a_slots):
            yield event.plain_result("你的队伍1没有任何上阵角色"); return
        if not any(n for _, n in b_slots):
            yield event.plain_result("对方队伍1没有任何上阵角色"); return

        try:
            result = await self.container.battle_service.simulate(uid, defender_uid)
        except Exception as e:
            yield event.plain_result(f"战斗模拟失败：{e}")
            return

        winner = result["winner"]
        probA, probB = result["prob"]["A"], result["prob"]["B"]
        label  = "我方胜" if winner=="A" else "对方胜"
        yield event.plain_result(
            f"战斗结果：{label}\n"
            f"胜率估计：我方 {int(probA*100)}% / 对方 {int(probB*100)}%\n"
            f"评估信心：{result.get('confidence','中')}\n"
            f"注意：本功能为临时测试，不结算战损。"
        )

    # 同盟子命令组
    @slg_group.group("同盟", alias={"联盟"})
    def alliance_group(self):
        pass

    @alliance_group.command("创建")
    async def alliance_create(self, event: AstrMessageEvent, name: str):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        if not self.res.get_or_none(uid):
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        ok, msg = self.container.alliance_service.create(uid, name)
        yield event.plain_result(msg)

    @alliance_group.command("加入")
    async def alliance_join(self, event: AstrMessageEvent, name: str):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        if not self.res.get_or_none(uid):
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        ok, msg = self.container.alliance_service.join(uid, name)
        yield event.plain_result(msg)

    @alliance_group.command("成员", alias={"成员列表"})
    async def alliance_members(self, event: AstrMessageEvent, name: str = None):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        if name:
            ok, title, ms = self.container.alliance_service.members(name)
        else:
            ok, title, ms = self.container.alliance_service.my_members(uid)
        if not ok:
            yield event.plain_result(title)
            return
        lines = [f"【{title}】成员（{len(ms)}人）:"]
        for m in ms:
            role = "领袖" if m["role"] == "leader" else "成员"
            lines.append(f"- {m['user_id']}（{role}）")
        yield event.plain_result("\n".join(lines))

    @alliance_group.command("列表", alias={"所有", "排行"})
    async def alliance_list_all(self, event: AstrMessageEvent):
        allys = self.container.alliance_service.list_all()
        if not allys:
            yield event.plain_result("当前没有任何同盟")
            return
        lines = ["同盟列表："]
        for a in allys:
            lines.append(f"- {a['name']} 领袖:{a['leader_user_id']} 人数:{a['members']}")
        yield event.plain_result("\n".join(lines))

    @alliance_group.command("帮助", alias={"help", "?", "？"})
    async def alliance_help(self, event: AstrMessageEvent):
        yield event.plain_result("用法：\n"
                                 "  slg 同盟 创建 名称\n"
                                 "  slg 同盟 加入 名称\n"
                                 "  slg 同盟 成员 [名称]    # 不填则查看自己所在同盟成员\n"
                                 "  slg 同盟 列表")

    @slg_group.command("资源", alias={"状态"})
    async def slg_resource_status(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
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

    @slg_group.command("队伍", alias={"编成", "编队"})
    async def slg_team(self, event: AstrMessageEvent, team_no: int = None):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p: 
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        self.container.team_service.ensure_teams(uid)
        if team_no:
            info = self.container.team_service.show_team(uid, team_no)
            m = "、".join([f"[{x['slot']}]{x['name']}Lv{x['level']}" if x['name'] else f"[{x['slot']}]空"
                           for x in info["members"]])
            yield event.plain_result(f"队伍{team_no}：{m}\n兵力 {info['soldiers']}/{info['capacity']}")
        else:
            infos = self.container.team_service.list_teams(uid)
            lines = []
            for info in infos:
                m = "、".join([f"[{x['slot']}]{x['name']}Lv{x['level']}" if x['name'] else f"[{x['slot']}]空"
                               for x in info["members"]])
                lines.append(f"队伍{info['team_no']}：{m} | 兵 {info['soldiers']}/{info['capacity']}")
            yield event.plain_result("\n".join(lines))

    @slg_group.command("上阵", alias={"加入队伍"})
    async def slg_assign_char(self, event: AstrMessageEvent, char_name: str, team_no: int, slot_idx: int = None):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p: 
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        if not char_name or not team_no:
            yield event.plain_result("用法：/slg 上阵 角色名 队伍编号 [槽位1-3]"); return
        try:
            team_no = int(team_no)
        except:
            yield event.plain_result("队伍编号必须是 1~3"); return
        self.container.team_service.ensure_teams(uid)
        ok, msg = self.container.team_service.assign(uid, char_name, team_no, slot_idx)
        yield event.plain_result(msg)

    @slg_group.command("补兵")
    async def slg_reinforce(self, event: AstrMessageEvent, team_no: int):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p: 
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        if not team_no:
            yield event.plain_result("用法：/slg 补兵 队伍编号"); return
        self.container.team_service.ensure_teams(uid)
        ok, msg, p2 = self.container.team_service.reinforce(p, team_no)
        yield event.plain_result(msg)

    @slg_group.command("升级")
    async def slg_upgrade(self, event: AstrMessageEvent, target_name: str):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p: 
            yield event.plain_result("还没加入。先用：/slg 加入"); return
        if not target_name:
            yield event.plain_result("用法：/slg 升级 <农田|钱庄|采石场|军营|角色名>"); return

        # 先判断是否建筑
        key = str(target_name).strip()
        bid = BUILDING_ALIASES.get(key, key)
        if bid in BUILDING_TO_RESOURCE:
            ok, msg, p = self.res.upgrade(p, key)
            yield event.plain_result(msg)
            return

        # 否则按“升级角色”
        ok, msg, p = self.container.team_service.upgrade_char(p, key)
        yield event.plain_result(msg)

    @slg_group.command("抽卡")
    async def slg_gacha(self, event: AstrMessageEvent, times: int = 1):
        uid = str(event.get_sender_id()); name = event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        
        times = max(1, min(50, times))  # 别让你一口气 999
        got, spent, done, status = self.container.gacha_service.draw(p, times)

        # 根据状态判断
        if status == DrawResultStatus.ALL_CHARACTERS_COLLECTED:
            yield event.plain_result("你已经集齐图鉴了，抽不出新角色。")
            return
        elif status == DrawResultStatus.NOT_ENOUGH_RESOURCES and done == 0:
            yield event.plain_result("资源不足，无法完成抽卡。")
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
