# main.py
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.api.star import Context, Star, register
from datetime import datetime, timedelta
import time

from .app.container import build_container
from .domain.constants import (
    BUILDING_ALIASES,
    BUILDING_TO_RESOURCE,
    RESOURCE_CN,
    DrawResultStatus,
    UPGRADE_STONE_COST,
    UPGRADE_RESOURCE_COST,
    MAX_LEVEL,
)


@register("astrbot_plugin_slg", "xunxiing", "SLG Map + Resource", "1.3.16", "https://github.com/xunxiing/astrbot_plugin_slg")
class HexPipelinePlugin(Star):
    def __init__(self, context: Context, config=None):
        super().__init__(context)
        llm_provider_id = config.get("llm_provider_id") if config else None
        self.container = build_container(context, config, llm_provider_id)
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
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        self.res.register(uid, name)
        self.container.base_service.ensure_base(uid)  # 新增：加入时自动分配基地
        yield event.plain_result("已加入。四建筑默认1级，开始自动产出。")

    @slg_group.command("帮助", alias={"help", "？", "?"})
    async def slg_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "用法：/slg 加入 | 资源 | 一键 | 升级 <农田/钱庄/采石场/军营> | 抽卡 <次数> | 基地 | 迁城 <城市名>"
        )

    @slg_group.command("进军", alias={"攻打", "开战"})
    async def slg_march(self, event: AstrMessageEvent, target: str):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        if not target.isdigit():
            yield event.plain_result("用法：slg 进军 对方ID（数字）")
            return
        defender_uid = target

        p_me = self.container.res_service.get_or_none(uid)
        if not p_me:
            yield event.plain_result("你还没加入游戏，先执行：slg 加入")
            return
        p_enemy = self.container.res_service.get_or_none(defender_uid)
        if not p_enemy:
            yield event.plain_result("对方未加入游戏")
            return

        # 保证队伍表存在
        self.container.team_service.ensure_teams(uid)
        self.container.team_service.ensure_teams(defender_uid)

        a_slots = self.container.res_service._repo.list_team_slots(uid, 1)
        b_slots = self.container.res_service._repo.list_team_slots(defender_uid, 1)
        if not any(n for _, n in a_slots):
            yield event.plain_result("你的队伍1没有任何上阵角色")
            return
        if not any(n for _, n in b_slots):
            yield event.plain_result("对方队伍1没有任何上阵角色")
            return

        try:
            result = await self.container.battle_service.simulate(uid, defender_uid)
        except Exception as e:
            yield event.plain_result(f"战斗模拟失败：{e}")
            return

        winner = result["winner"]
        probA, probB = result["prob"]["A"], result["prob"]["B"]
        label = "我方胜" if winner == "A" else "对方胜"
        yield event.plain_result(
            f"战斗结果：{label}\n"
            f"胜率估计：我方 {int(probA * 100)}% / 对方 {int(probB * 100)}%\n"
            f"评估信心：{result.get('confidence', '中')}\n"
            f"注意：本功能为临时测试，不结算战损。"
        )

    # 同盟子命令组
    @slg_group.group("同盟", alias={"联盟"})
    def alliance_group(self):
        pass

    @alliance_group.command("创建")
    async def alliance_create(self, event: AstrMessageEvent, name: str):
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        if not self.res.get_or_none(uid):
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        ok, msg = self.container.alliance_service.create(uid, name)
        yield event.plain_result(msg)

    @alliance_group.command("加入")
    async def alliance_join(self, event: AstrMessageEvent, name: str):
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
        if not self.res.get_or_none(uid):
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        ok, msg = self.container.alliance_service.join(uid, name)
        yield event.plain_result(msg)

    @alliance_group.command("成员", alias={"成员列表"})
    async def alliance_members(self, event: AstrMessageEvent, name: str = None):
        uid = str(event.get_sender_id())
        name = event.get_sender_name() or uid
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

    @slg_group.command("一键", alias={"daily", "一键日常"})
    async def slg_one_tap(self, event: AstrMessageEvent):
        """一键日常：结算→汇总→建议下一步。
        仅展示建议，不自动执行任何消耗性操作。
        """
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return

        # 1) 资源结算 & 基本状态
        p = self.res.settle(p)
        self.container.team_service.ensure_teams(uid)
        s = self.res.status(p)
        lvb = s["level_by_building"]
        prod = s["prod_per_min"]
        cap = s["cap"]
        cur = s["cur"]

        # 2) 可升清单 & 缺口估算
        def _fmt_cost(res_type: str, stone_need: int, res_need: int) -> str:
            if res_type == "stone":
                return f"石头 {stone_need + res_need}"
            return f"石头 {stone_need}，{RESOURCE_CN[res_type]} {res_need}"

        affordable = []
        next_gaps = []
        show_order = ["farm", "bank", "quarry", "barracks"]
        cn_name = {"farm": "农田", "bank": "钱庄", "quarry": "采石场", "barracks": "军营"}
        for bid in show_order:
            cur_lv = int(lvb[bid])
            if cur_lv >= MAX_LEVEL:
                continue
            res_type = BUILDING_TO_RESOURCE[bid]
            stone_need = UPGRADE_STONE_COST[bid][cur_lv + 1]
            res_need = UPGRADE_RESOURCE_COST[res_type][cur_lv + 1]
            have_stone = cur["stone"]
            have_res = cur[res_type]
            stone_ok = have_stone >= (stone_need + (res_need if res_type == "stone" else 0))
            res_ok = (have_res >= res_need) if res_type != "stone" else True
            if stone_ok and res_ok:
                affordable.append(f"{cn_name[bid]}→{cur_lv+1}级（{_fmt_cost(res_type, stone_need, res_need)}）")
            else:
                # 估算到达下一档所需分钟（取石头/自身资源两者的最大时间）
                need_stone = max(0, stone_need + (res_need if res_type == "stone" else 0) - have_stone)
                need_res = 0 if res_type == "stone" else max(0, res_need - have_res)
                t1 = float("inf") if prod["stone"] <= 0 else (need_stone / max(1, prod["stone"]))
                t2 = 0 if res_type == "stone" else (float("inf") if prod[res_type] <= 0 else (need_res / max(1, prod[res_type])))
                eta_min = int(t1 if t1 > t2 else t2)
                gap_parts = []
                if need_stone > 0:
                    gap_parts.append(f"石头缺{need_stone}")
                if need_res > 0:
                    gap_parts.append(f"{RESOURCE_CN[res_type]}缺{need_res}")
                next_gaps.append(f"{cn_name[bid]}→{cur_lv+1}级 缺口：{'，'.join(gap_parts)}（约 {eta_min} 分钟）")

        # 3) 编成与补兵建议
        owned = self.res._repo.list_owned_char_names(uid)  # 仅读
        slots = self.res._repo.list_team_slots(uid, 1)
        assigned_any = any(name for _, name in slots)
        cap1 = self.container.team_service.calc_capacity(uid, 1)
        cur1 = self.res._repo.get_team_soldiers(uid, 1)

        suggestions = []
        # 优先级：没角色→抽卡；有角色未上阵→上阵；可补兵→补兵；可升→升级；否则提示等待
        if not owned:
            # 下次单抽价格（预览）
            nxt = getattr(p, "draw_count", 0) + 1
            if hasattr(self.container.gacha_service, "cost_for_draw_index"):
                c = self.container.gacha_service.cost_for_draw_index(nxt)
                suggestions.append(
                    f"建议：/slg 抽卡 10（下次单抽费用 预览：金{c['gold']} 粮{c['grain']} 石{c['stone']} 兵{c['troops']}）"
                )
            else:
                suggestions.append("建议：/slg 抽卡 10")
        elif not assigned_any:
            name = owned[0]
            suggestions.append(f"建议：/slg 上阵 {name} 1  # 先把角色上到队伍1")
        elif cur1 < cap1 and p.troops > 0:
            suggestions.append("建议：/slg 补兵 1  # 队伍1未满编")
        elif affordable:
            # 简单推荐第一条可升（更复杂的性价比可后续扩展）
            first = affordable[0]
            bname = first.split("→", 1)[0]
            suggestions.append(f"建议：/slg 升级 {bname}")
        else:
            # 兜底：按缺口里最快的一项给等待提示
            wait_tip = next_gaps[0] if next_gaps else "资源已接近上限，可视情况升级或抽卡"
            suggestions.append(f"建议：等待一会儿产出（{wait_tip}）")

        # 4) 输出
        lines = []
        lines.append(
            f"建筑：农田{lvb['farm']} 钱庄{lvb['bank']} 采石场{lvb['quarry']} 军营{lvb['barracks']}"
        )
        lines.append(
            f"产出/分：粮{prod['grain']} 金{prod['gold']} 石{prod['stone']} 兵{prod['troops']}"
        )
        lines.append(
            f"资源：粮{cur['grain']}/{cap['grain']} 金{cur['gold']}/{cap['gold']} 石{cur['stone']}/{cap['stone']} 兵{cur['troops']}/{cap['troops']}"
        )
        if affordable:
            lines.append("可直接升级：" + "；".join(affordable))
        if next_gaps:
            lines.append("下一档缺口：\n- " + "\n- ".join(next_gaps))
        lines.append(
            f"队伍1：成员{'有' if assigned_any else '无'}｜兵 {cur1}/{cap1}（仓库兵 {p.troops}）"
        )
        lines.extend(suggestions)
        yield event.plain_result("\n".join(lines))

    @alliance_group.command("列表", alias={"所有", "排行"})
    async def alliance_list_all(self, event: AstrMessageEvent):
        allys = self.container.alliance_service.list_all()
        if not allys:
            yield event.plain_result("当前没有任何同盟")
            return
        lines = ["同盟列表："]
        for a in allys:
            lines.append(
                f"- {a['name']} 领袖:{a['leader_user_id']} 人数:{a['members']}"
            )
        yield event.plain_result("\n".join(lines))

    @staticmethod
    def _parse_time_local(s: str) -> int | None:
        """
        支持两种格式：
          1) 'YYYY-MM-DD HH:MM'
          2) 'HH:MM'（今天该时刻，若已过则默认明天）
        返回 epoch 秒；失败返回 None
        """
        s = (s or "").strip()
        try:
            if len(s) >= 16:
                dt = datetime.strptime(s, "%Y-%m-%d %H:%M")
            else:
                hh, mm = s.split(":")
                now = datetime.fromtimestamp(time.time())
                dt = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
                if dt.timestamp() <= time.time():
                    dt = dt + timedelta(days=1)
            return int(dt.timestamp())
        except Exception:
            return None

    @alliance_group.command("攻城")
    async def cmd_alliance_siege(self, event: AstrMessageEvent, city: str, when: str):
        """
        发起同盟攻城：slg 同盟 攻城 城市名 预定时间
        时间支持：'YYYY-MM-DD HH:MM' 或 'HH:MM'（当天，若已过则默认明天）
        仅领袖可发起；一个同盟同一时间仅允许一个进行中的计划。
        """
        uid = str(event.get_sender_id())
        start_at = HexPipelinePlugin._parse_time_local(when)
        if not start_at:
            yield event.plain_result(
                "时间格式错误。示例：'2025-09-02 20:30' 或 '20:30'"
            )
            return
        if start_at - int(time.time()) < 10 * 60:
            yield event.plain_result("预定时间需要在10分钟之后")
            return
        ok, msg = self.container.siege_service.schedule_siege(
            uid, city.strip(), start_at
        )
        yield event.plain_result(msg)

    @alliance_group.command("集结")
    async def cmd_alliance_rally(self, event: AstrMessageEvent):
        """
        参与当前同盟最近一次攻城计划：slg 同盟 集结
        将从你的"基地城市"按最短路径出发，按每段 SIEGE_EDGE_MINUTES 分钟估算 ETA。
        """
        uid = str(event.get_sender_id())
        ok, msg = self.container.siege_service.join_rally(uid)
        yield event.plain_result(msg)

    @alliance_group.command("攻城状态")
    async def cmd_alliance_siege_status(self, event: AstrMessageEvent):
        """
        查看攻城状态并在到期时自动结算：slg 同盟 攻城状态
        结算口径：30分钟窗口累计攻城点数 >= 城市等级阈值则成功。
        """
        uid = str(event.get_sender_id())
        ok, msg = self.container.siege_service.status_and_maybe_finalize(uid)
        yield event.plain_result(msg if ok else f"查询失败：{msg}")

    @alliance_group.command("帮助", alias={"help", "?", "？"})
    async def alliance_help(self, event: AstrMessageEvent):
        yield event.plain_result(
            "用法：\n"
            "  slg 同盟 创建 名称\n"
            "  slg 同盟 加入 名称\n"
            "  slg 同盟 成员 [名称]    # 不填则查看自己所在同盟成员\n"
            "  slg 同盟 列表\n"
            "  slg 同盟 攻城 城市名 时间\n"
            "  slg 同盟 集结\n"
            "  slg 同盟 攻城状态"
        )

    @slg_group.command("资源", alias={"状态"})
    async def slg_resource_status(self, event: AstrMessageEvent):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        # 懒结算
        p = self.res.settle(p)
        s = self.res.status(p)
        lvb = s["level_by_building"]  # 这里用建筑键名
        prod = s["prod_per_min"]
        cap = s["cap"]
        cur = s["cur"]

        lines = [
            f"建筑等级：农田{lvb['farm']} 钱庄{lvb['bank']} 采石场{lvb['quarry']} 军营{lvb['barracks']}",
            f"产出/分钟：粮{prod['grain']} 金{prod['gold']} 石{prod['stone']} 兵{prod['troops']}",
            f"当前/上限：粮{cur['grain']}/{cap['grain']} 金{cur['gold']}/{cap['gold']} 石{cur['stone']}/{cap['stone']} 兵{cur['troops']}/{cap['troops']}",
        ]
        yield event.plain_result("\n".join(lines))

    @slg_group.command("队伍", alias={"编成", "编队"})
    async def slg_team(self, event: AstrMessageEvent, team_no: int = None):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        self.container.team_service.ensure_teams(uid)
        if team_no:
            info = self.container.team_service.show_team(uid, team_no)
            m = "、".join(
                [
                    f"[{x['slot']}]{x['name']}Lv{x['level']}"
                    if x["name"]
                    else f"[{x['slot']}]空"
                    for x in info["members"]
                ]
            )
            yield event.plain_result(
                f"队伍{team_no}：{m}\n兵力 {info['soldiers']}/{info['capacity']}"
            )
        else:
            infos = self.container.team_service.list_teams(uid)
            lines = []
            for info in infos:
                m = "、".join(
                    [
                        f"[{x['slot']}]{x['name']}Lv{x['level']}"
                        if x["name"]
                        else f"[{x['slot']}]空"
                        for x in info["members"]
                    ]
                )
                lines.append(
                    f"队伍{info['team_no']}：{m} | 兵 {info['soldiers']}/{info['capacity']}"
                )
            yield event.plain_result("\n".join(lines))

    @slg_group.command("上阵", alias={"加入队伍"})
    async def slg_assign_char(
        self,
        event: AstrMessageEvent,
        char_name: str,
        team_no: int,
        slot_idx: int = None,
    ):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        if not char_name or not team_no:
            yield event.plain_result("用法：/slg 上阵 角色名 队伍编号 [槽位1-3]")
            return
        try:
            team_no = int(team_no)
        except (ValueError, TypeError):
            yield event.plain_result("队伍编号必须是 1~3")
            return
        self.container.team_service.ensure_teams(uid)
        ok, msg = self.container.team_service.assign(uid, char_name, team_no, slot_idx)
        yield event.plain_result(msg)

    @slg_group.command("补兵")
    async def slg_reinforce(self, event: AstrMessageEvent, team_no: int):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        if not team_no:
            yield event.plain_result("用法：/slg 补兵 队伍编号")
            return
        self.container.team_service.ensure_teams(uid)
        ok, msg, p2 = self.container.team_service.reinforce(p, team_no)
        yield event.plain_result(msg)

    @slg_group.command("升级")
    async def slg_upgrade(self, event: AstrMessageEvent, target_name: str):
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
        p = self.res.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：/slg 加入")
            return
        if not target_name:
            yield event.plain_result("用法：/slg 升级 <农田|钱庄|采石场|军营|角色名>")
            return

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
        uid = str(event.get_sender_id())
        event.get_sender_name() or uid
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
            for k in ("gold", "grain", "stone", "troops"):
                if spent[k] > 0:
                    cn = {
                        "gold": "金钱",
                        "grain": "粮食",
                        "stone": "石头",
                        "troops": "军队",
                    }[k]
                    cost_str.append(f"{cn}{spent[k]}")
            if cost_str:
                lines.append("总消耗：" + "，".join(cost_str))
        else:
            lines.append("资源不足，无法完成抽卡。")

        # 附加提示：下次单抽价格预览（不收费）
        nxt = p.draw_count + 1
        cst = (
            self.container.gacha_service.cost_for_draw_index(nxt)
            if hasattr(self.container.gacha_service, "cost_for_draw_index")
            else None
        )
        if cst:
            lines.append(
                f"下次单抽费用：金{cst['gold']} 粮{cst['grain']} 石{cst['stone']} 兵{cst['troops']}（前5次免费，6-15线性涨，之后恒定）"
            )

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
                data={},  # 目前没用到变量，留空即可
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
        img_url = await self.html_render(
            tmpl=html,
            data={},
            return_url=True,
            options={"type": "png", "full_page": True},
        )
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
            parts.append(
                f"{gate} → {nb} | 里程碑：{mi + 1}/3（{['前沿', '箭楼', '外城门'][mi]}）| 进度：{pr}%"
            )
        yield event.plain_result(
            f"{city}（{c.province}州{'·州府' if c.capital else ''}）：\n"
            + "\n".join(parts)
        )

    @filter.command("line_push")
    async def push_line(
        self, event: AstrMessageEvent, city: str, gate: str, delta: int
    ):
        """占位推进：为某城某门推进 delta%（0-100）"""
        if gate not in ("北门", "东门", "西门", "南门", "西北门"):  # 简易容错
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
        yield event.plain_result(
            f"已推进 {city} {gate} → {nb}，现在：{['前沿', '箭楼', '外城门'][mi]} {pr}%"
        )

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

    @slg_group.command("基地")
    async def slg_base(self, event: AstrMessageEvent):
        """查看或自动分配基地（首次进入自动分配到四州之一）"""
        uid = str(event.get_sender_id())
        p = self.container.res_service.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：slg 加入")
            return
        ok, msg = self.container.base_service.ensure_base(uid)
        yield event.plain_result(msg)

    @slg_group.command("迁城")
    async def slg_move_capital(self, event: AstrMessageEvent, city: str):
        """
        迁城到指定城市（每天一次；仅允许 益/扬/冀/兖 四州）
        用法：slg 迁城 城市名
        """
        uid = str(event.get_sender_id())
        p = self.container.res_service.get_or_none(uid)
        if not p:
            yield event.plain_result("还没加入。先用：slg 加入")
            return

        # 确保已有基地（新号会自动分配）
        _ok, _ = self.container.base_service.ensure_base(uid)

        target = (city or "").strip()
        if not target:
            yield event.plain_result("用法：slg 迁城 城市名")
            return

        ok, msg = self.container.base_service.migrate(uid, target)
        yield event.plain_result(msg)
