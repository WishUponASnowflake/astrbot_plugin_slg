# app_pipeline/stages.py
from typing import Any, Dict, Callable, Awaitable
from .pipeline import BaseStage


class NormalizeStage(BaseStage):
    async def handle(
        self,
        ctx: Dict[str, Any],
        nxt: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
    ):
        # 占位：统一大小写、修剪参数等
        for k in ("src", "dst"):
            if isinstance(ctx.get(k), str):
                ctx[k] = ctx[k].strip()
        ctx["normalized"] = True
        return await nxt(ctx)


class AuditStage(BaseStage):
    async def handle(
        self,
        ctx: Dict[str, Any],
        nxt: Callable[[Dict[str, Any]], Awaitable[Dict[str, Any]]],
    ):
        # 占位：记录审计信息（这里就打个标记）
        ctx["audit"] = {"ok": True}
        return await nxt(ctx)
