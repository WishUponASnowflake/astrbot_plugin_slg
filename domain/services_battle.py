# domain/services_battle.py
from __future__ import annotations
import json
from typing import Dict, Any, List, Optional
from ..infra.astr_llm import AstrLLM

# 关键词特征：精简版（只看技能文案，不引入地形/天气）
KW = {
    "combat":   ["伤害","爆发","斩","破甲","范围","AOE","火焰","雷","穿刺","暴击","连击","重击","追击","射击"],
    "control":  ["控制","眩晕","击退","缴械","减速","禁疗","恐慌","沉默","扰乱","定身","嘲讽"],
    "morale_p": ["鼓舞","士气","军心","威慑","震慑","号令","指挥","士气回复"],
    "morale_n": ["自残","流血","衰减","恐惧","怯战","崩溃","退却"],
    "sustain":  ["治疗","回复","再生","护盾","格挡","减伤","护主","庇护","防御姿态","恢复"],
    "mobility": ["机动","突击","冲锋","闪避","位移","穿行","游走","突进","骑射"],
    "logistics":["补给","后勤","粮草","运输","续航","弹药","工程"],
}

AXES = [
    "目标清晰度","兵员质量","领导与指挥","情报与欺骗",
    "兵种协同","火力与续航","士气与阈值","战术灵活度",
    "开局部署","奇袭窗口","控制与干扰","生存与回复"
]
JUDGE_MAP = {"A优":2,"A略优":1,"对等":0,"B略优":-1,"B优":-2}
WEIGHTS = {
    "目标清晰度":0.08,"兵员质量":0.10,"领导与指挥":0.12,"情报与欺骗":0.06,
    "兵种协同":0.10,"火力与续航":0.10,"士气与阈值":0.10,"战术灵活度":0.12,
    "开局部署":0.07,"奇袭窗口":0.05,"控制与干扰":0.05,"生存与回复":0.05,
}

ASSESS_SYSTEM = (
  "你是战术分析裁判。只输出 JSON。字段："
  "axes[{name,judge('A优'|'A略优'|'对等'|'B略优'|'B优'),rationale}], "
  "phase_votes{opening:'A'|'B'|'平', maneuver:'A'|'B'|'平', decisive:'A'|'B'|'平'}, "
  "who_wins_if_forced('A'|'B'), confidence。"
  "axes 名称顺序必须严格为："+",".join(AXES)+"。最多一个“对等”。"
)
ASSESS_USER_TMPL = (
  "两军：{teams}\n"
  "A方技能特征：{featA}\nB方技能特征：{featB}\n"
  "不考虑地形/天气，只基于兵力与技能判断。只输出 JSON。"
)

TIE_SYSTEM = "你是果断的军事裁判，只输出JSON。"
TIE_USER_TMPL = "五个微场景裁决，只输出 JSON：{{\"votes\":[(\"A\"|\"B\"|\"平\"),...]}}，长度为5。上下文：{ctx}"

def _text(s: Any) -> str:
    if isinstance(s, str): return s
    if isinstance(s, dict):
        buf=[]
        for k in ("name","description","desc","effect","effects","tags","label","labels"):
            v=s.get(k)
            if isinstance(v, list): buf += [str(x) for x in v]
            elif v is not None: buf.append(str(v))
        return " ".join(buf)
    return ""

from ..domain.entities import Character, Skill # 新增

def _extract_features(members: List[Character]) -> Dict[str,float]:
    counts = {k:0 for k in KW}; total=0
    for role in members:
        skills = role.skills or []
        for s in skills:
            t=_text(s).lower()
            if not t: continue
            total+=1
            for key, lst in KW.items():
                counts[key] += sum(1 for kw in lst if kw.lower() in t)
    total=max(1,total)
    def norm(v): return round(min(1.0, v/max(3,total)),3)
    combat   = norm(counts["combat"])
    control  = norm(counts["control"])
    morale   = round(max(0.0, min(1.0, (counts["morale_p"] - 0.7*counts["morale_n"])/max(3,total) + 0.5)),3)
    sustain  = norm(counts["sustain"])
    mobility = norm(counts["mobility"])
    logistics= norm(counts["logistics"])
    return {"combat":combat,"control":control,"morale":morale,"sustain":sustain,"mobility":mobility,"logistics":logistics}

def _agg_axes(axes: List[Dict[str,Any]]) -> int:
    s=0; eq=0
    for item in axes:
        val = JUDGE_MAP.get(item.get("judge"),0)
        if item.get("judge")=="对等":
            eq+=1
            if eq>1: val=0
        s += round(val * (WEIGHTS.get(item.get("name",""),0.08)*10))
    return s

def _phase_score(v: Dict[str,str]) -> int:
    sc=0
    for k in ("opening","maneuver","decisive"):
        x=v.get(k,"平"); sc += 1 if x=="A" else -1 if x=="B" else 0
    return sc

def _s_to_prob(S:int)->float:
    if S>=9: return 0.8
    if S>=6: return 0.7
    if S>=3: return 0.6
    if S>=1: return 0.55
    if S<=-9: return 0.2
    if S<=-6: return 0.3
    if S<=-3: return 0.4
    if S<=-1: return 0.45
    return 0.5

class BattleService:
    """
    从仓库读双方“队伍1”的成员与真实兵力；用 AstrLLM 做结构化判定；返回胜负与概率。
    不使用环境，简单、可控、够测。
    """
    def __init__(self, repo, chars_pool: List[Character], context):
        self._repo = repo
        self._chars = {c.name: c for c in chars_pool if hasattr(c, "name")}
        self._llm = AstrLLM(context)

    def _members(self, names: List[str])->List[Character]:
        return [self._chars[n] for n in names if n in self._chars]

    async def simulate(self, attacker_uid: str, defender_uid: str) -> Dict[str,Any]:
        # 读双方队伍1与“当前兵力”（不是上限）
        a_slots = self._repo.list_team_slots(attacker_uid, 1)
        b_slots = self._repo.list_team_slots(defender_uid, 1)
        A = [name for _, name in a_slots if name]
        B = [name for _, name in b_slots if name]
        soldiersA = self._repo.get_team_soldiers(attacker_uid, 1)
        soldiersB = self._repo.get_team_soldiers(defender_uid, 1)
        if not A or not B:
            raise RuntimeError("任一方队伍1为空，无法开战")

        teams = {"teams":[{"side":"A","members":A,"soldiers":soldiersA},
                          {"side":"B","members":B,"soldiers":soldiersB}]}
        featA = _extract_features(self._members(A))
        featB = _extract_features(self._members(B))

        assess_user = ASSESS_USER_TMPL.format(
            teams=json.dumps(teams, ensure_ascii=False),
            featA=json.dumps(featA, ensure_ascii=False),
            featB=json.dumps(featB, ensure_ascii=False),
        )
        raw = await self._llm.chat_json(ASSESS_SYSTEM, assess_user, temperature=0.2)
        axes = raw.get("axes", [])
        if len(axes) != len(AXES):
            raise RuntimeError(f"axes 数量不符，预期 {len(AXES)}，实际 {len(axes)}")

        S  = _agg_axes(axes)
        S += _phase_score(raw.get("phase_votes",{}))

        # 给兵力差一个小权重，避免“技多不压身”把 5 人打 5000 人
        diff = (soldiersA - soldiersB) / max(1, soldiersA + soldiersB)
        if diff > 0.25:   S += 2
        elif diff > 0.10: S += 1
        elif diff < -0.25:S -= 2
        elif diff < -0.10:S -= 1

        pA = _s_to_prob(S); pB = 1 - pA

        # 如果五五开，加一次五场微裁决
        if 0.48 <= pA <= 0.52:
            ctx = {"teams":teams,"axes":axes,"phase_votes":raw.get("phase_votes",{})}
            tb = await self._llm.chat_json(TIE_SYSTEM, TIE_USER_TMPL.format(ctx=json.dumps(ctx, ensure_ascii=False)), temperature=0.1)
            votes = (tb.get("votes") or [])[:5]
            dv = sum(+1 if v=="A" else -1 if v=="B" else 0 for v in votes)
            if dv > 0: pA = min(0.53, pA + 0.03)
            elif dv < 0: pA = max(0.47, pA - 0.03)
            pB = 1 - pA

        winner = "A" if pA >= pB else "B"
        return {"winner": winner, "prob": {"A": round(pA,3), "B": round(pB,3)},
                "confidence": raw.get("confidence","中"), "teams": teams}
