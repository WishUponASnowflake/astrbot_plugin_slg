# domain/services_gacha.py
import time, math, random
from typing import Dict, List, Tuple
from .ports import PlayerRepositoryPort
from .entities import Player, Character
from .constants import RESOURCE_CN
from .services_resources import ResourceService

def _linear_cost(n: int, start: int, end: int) -> int:
    # n ∈ [6,15] 线性插值；n<6 用 start；n>15 用 end
    if n <= 5: return 0
    if n >= 15: return end
    t = (n - 6) / 9.0
    return int(round(start + t * (end - start)))

def cost_for_draw_index(n: int) -> Dict[str, int]:
    # 前5次免费；6–15线性；>15恒定为第15次
    return {
        "gold":   0 if n<=5 else _linear_cost(n, 10, 1000),
        "grain":  0 if n<=5 else _linear_cost(n, 10,  800),
        "stone":  0 if n<=5 else _linear_cost(n, 10,  500),
        "troops": 0 if n<=5 else _linear_cost(n, 10, 1000),
    }

class GachaService:
    cost_for_draw_index = staticmethod(cost_for_draw_index) # 类内部挂个同名静态代理方便 main 调用

    def __init__(self, repo: PlayerRepositoryPort, res: ResourceService, pool: List[Character]):
        self._repo = repo
        self._res = res
        self._pool = pool

    def _now(self) -> int:
        return int(time.time())

    def _pick_one(self, remains: List[Character]) -> Character:
        # 均匀随机；以后你要加权我再给你做概率厨艺
        return random.choice(remains)

    def draw(self, p: Player, count: int) -> Tuple[List[Character], Dict[str,int], int]:
        """
        返回：获得的角色列表、实际消耗汇总、成功抽取次数
        会自动结算资源并扣费；不够则提前停。
        """
        # 全图鉴判断
        owned = self._repo.list_owned_char_names(p.user_id)
        remains = [c for c in self._pool if c.name not in owned]
        if not remains:
            return [], {"gold":0,"grain":0,"stone":0,"troops":0}, 0

        got: List[Character] = []
        spent = {"gold":0,"grain":0,"stone":0,"troops":0}

        # 先懒结算资源
        p = self._res.settle(p)

        for i in range(count):
            # 再次检查是否还有可抽
            owned = self._repo.list_owned_char_names(p.user_id)
            remains = [c for c in self._pool if c.name not in owned]
            if not remains:
                break

            draw_index = p.draw_count + 1  # 下一个抽的序号（从1开始）
            cost = cost_for_draw_index(draw_index)

            # 余额是否足够
            enough = (p.gold  >= cost["gold"]  and
                      p.grain >= cost["grain"] and
                      p.stone >= cost["stone"] and
                      p.troops>= cost["troops"])
            if not enough:
                break

            # 扣费
            p.gold  -= cost["gold"]
            p.grain -= cost["grain"]
            p.stone -= cost["stone"]
            p.troops-= cost["troops"]

            for k in spent: spent[k] += cost[k]

            # 发卡
            ch = self._pick_one(remains)
            self._repo.add_character(p.user_id, ch.name, level=1, obtained_at=self._now())
            got.append(ch)

            # 计数 +1 并落库
            p.draw_count += 1
            self._repo.upsert_player(p)

        return got, spent, len(got)
