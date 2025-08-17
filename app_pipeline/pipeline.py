# app_pipeline/pipeline.py
from typing import Any, Awaitable, Callable, Dict, List, Optional

StageFn = Callable[[Dict[str, Any], Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]], Awaitable[Dict[str, Any]]]

class Pipeline:
    def __init__(self, stages: List["BaseStage"]):
        self._stages = stages

    async def run(self, ctx: Dict[str, Any], initial_payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        async def terminal(c: Dict[str, Any]) -> Dict[str, Any]:
            return c

        next_fn = terminal
        for stage in reversed(self._stages):
            prev_next = next_fn
            async def make_next(s=stage, n=prev_next):
                async def _next(c: Dict[str, Any]) -> Dict[str, Any]:
                    return await s.handle(c, n)
                return _next
            next_fn = await make_next()

        start_ctx = ctx.copy()
        if initial_payload:
            start_ctx.update(initial_payload)
        return await next_fn(start_ctx)

class BaseStage:
    async def handle(self, ctx: Dict[str, Any], nxt: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]]) -> Dict[str, Any]:
        return await nxt(ctx)
