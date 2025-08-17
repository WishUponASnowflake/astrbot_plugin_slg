# infra/hooks.py
from typing import Any, Awaitable, Callable, Dict, List

HookHandler = Callable[[Dict[str, Any]], Awaitable[None]]

class HookBus:
    def __init__(self):
        self._handlers = {}  # name -> List[HookHandler]

    def on(self, name: str, handler: HookHandler):
        self._handlers.setdefault(name, []).append(handler)

    async def emit(self, name: str, payload: Dict[str, Any]):
        for h in self._handlers.get(name, []):
            await h(payload)
