# infra/character_provider.py
import json
from pathlib import Path
from typing import List
from ..domain.entities import Character, Skill

class CharacterProvider:
    def __init__(self, json_path: Path):
        self._path = Path(json_path)

    def load_all(self) -> List[Character]:
        data = json.loads(self._path.read_text(encoding="utf-8"))
        out: List[Character] = []
        for item in data:
            skills = [Skill(name=s["name"], description=s["description"]) for s in item.get("skills", [])]
            out.append(Character(
                name=item["name"], title=item.get("title",""), background=item.get("background",""), skills=skills
            ))
        return out
