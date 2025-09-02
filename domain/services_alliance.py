import time
from typing import Tuple, List, Dict
from .ports import PlayerRepositoryPort
from .constants import ALLIANCE_MAX_MEMBERS


class AllianceService:
    def __init__(self, repo: PlayerRepositoryPort):
        self._repo = repo

    def _now(self) -> int:
        return int(time.time())

    # 创建同盟：创建者自动成为领袖并加入
    def create(self, user_id: str, name: str) -> Tuple[bool, str]:
        name = name.strip()
        if not name:
            return False, "同盟名不能为空"

        if self._repo.get_user_alliance(user_id):
            return False, "已加入其他同盟，不能重复创建"

        if self._repo.get_alliance_by_name(name):
            return False, "同盟名已存在"

        aid = self._repo.create_alliance(name, user_id, self._now())
        self._repo.add_member_to_alliance(aid, user_id, "leader", self._now())
        return True, f"创建成功：{name}（你是领袖）"

    # 加入同盟：满员拒绝；一人一盟
    def join(self, user_id: str, name: str) -> Tuple[bool, str]:
        name = name.strip()
        if not name:
            return False, "同盟名不能为空"

        if self._repo.get_user_alliance(user_id):
            return False, "已加入其他同盟"

        a = self._repo.get_alliance_by_name(name)
        if not a:
            return False, "不存在的同盟"

        cnt = self._repo.count_alliance_members(a["id"])
        if cnt >= ALLIANCE_MAX_MEMBERS:
            return False, f"同盟已满（{cnt}/{ALLIANCE_MAX_MEMBERS}）"

        self._repo.add_member_to_alliance(a["id"], user_id, "member", self._now())
        return True, f"加入成功：{name}"

    # 查询某同盟成员
    def members(self, name: str) -> Tuple[bool, str, List[Dict]]:
        a = self._repo.get_alliance_by_name(name.strip())
        if not a:
            return False, "不存在的同盟", []
        ms = self._repo.list_alliance_members(a["id"])
        return True, a["name"], ms

    # 查询我所在同盟及成员
    def my_members(self, user_id: str) -> Tuple[bool, str, List[Dict]]:
        a = self._repo.get_user_alliance(user_id)
        if not a:
            return False, "未加入任何同盟", []
        ms = self._repo.list_alliance_members(a["id"])
        return True, a["name"], ms

    # 列出所有同盟（带人数）
    def list_all(self) -> List[Dict]:
        return self._repo.list_alliances()
