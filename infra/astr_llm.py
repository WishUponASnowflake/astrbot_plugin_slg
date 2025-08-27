# infra/astr_llm.py
import json

class AstrLLM:
    """
    用 AstrBot Provider 调 LLM，并强制拿到 JSON。
    - system 放进 contexts，避免覆盖 AstrBot 自己的 system_prompt。
    - 对非纯 JSON 的输出做一次大括号截断兜底。
    """
    def __init__(self, context):
        self.context = context
        self.provider = context.get_using_provider()
        if not self.provider:
            raise RuntimeError("AstrBot LLM Provider 未配置或不可用。请检查 AstrBot 的 LLM 设置。")
        self.func_tools = context.get_llm_tool_manager()

    async def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        resp = await self.provider.text_chat(
            prompt=user,
            session_id=None,          # 已废弃，不用
            contexts=[{"role": "system", "content": system}],
            image_urls=[],
            func_tool=self.func_tools,
            system_prompt=""          # 刻意留空，避免双 system
        )
        text = getattr(resp, "completion_text", None)
        if not text and getattr(resp, "raw_completion", None):
            try:
                text = resp.raw_completion["choices"][0]["message"]["content"]
            except Exception:
                text = None
        if not text:
            raise RuntimeError("LLM 无有效文本响应")
        try:
            return json.loads(text)
        except Exception:
            s, e = text.find("{"), text.rfind("}")
            if s != -1 and e != -1 and e > s:
                return json.loads(text[s:e+1])
            raise RuntimeError(f"LLM 未返回可解析 JSON：{text[:200]}")
