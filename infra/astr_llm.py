# infra/astr_llm.py
import json


class AstrLLM:
    """
    用 AstrBot Provider 调 LLM，并强制拿到 JSON。
    - system 放进 contexts，避免覆盖 AstrBot 自己的 system_prompt。
    - 对非纯 JSON 的输出做一次大括号截断兜底。
    """

    def __init__(self, context, llm_provider_id: str = None):
        self.context = context
        if llm_provider_id:
            self.provider = context.get_provider_by_id(llm_provider_id)
            if not self.provider:
                print(
                    f"[WARN] 插件配置的 LLM Provider ID '{llm_provider_id}' 未找到或不可用。将尝试使用 AstrBot 的默认 LLM Provider。"
                )
                self.provider = context.get_using_provider()
        else:
            self.provider = context.get_using_provider()

        if not self.provider:
            print("[WARN] AstrBot LLM Provider 未配置或不可用。LLM 功能将受限。")
        self.func_tools = context.get_llm_tool_manager()

    async def chat_json(self, system: str, user: str, temperature: float = 0.2) -> dict:
        if not self.provider:
            print("[WARN] LLM Provider 不可用，返回模拟响应。")
            # 返回一个默认的模拟响应，避免插件崩溃
            return {
                "response": "LLM Provider 未配置，无法生成响应。请检查 AstrBot 的 LLM 设置。",
                "parsed": True,
            }

        resp = await self.provider.text_chat(
            prompt=user,
            session_id=None,  # 已废弃，不用
            contexts=[{"role": "system", "content": system}],
            image_urls=[],
            func_tool=self.func_tools,
            system_prompt="",  # 刻意留空，避免双 system
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
                return json.loads(text[s : e + 1])
            raise RuntimeError(f"LLM 未返回可解析 JSON：{text[:200]}")
