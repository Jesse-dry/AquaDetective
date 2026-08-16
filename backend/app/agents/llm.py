"""LLM 客户端封装：OpenAI 兼容；不可用/失败时返回 None，由调用方走模板降级。

保证：演示现场无网/无 key 也能完成完整推理流程（模板推理）。
"""
from __future__ import annotations

import json

from ..config import Settings


class LLMClient:
    def __init__(self, settings_: Settings):
        self.settings = settings_
        self.client = None
        if settings_.llm_api_key:
            try:
                from openai import OpenAI
                kwargs: dict = {"api_key": settings_.llm_api_key}
                if settings_.llm_base_url:
                    kwargs["base_url"] = settings_.llm_base_url
                self.client = OpenAI(**kwargs)
            except Exception:
                self.client = None

    @property
    def available(self) -> bool:
        return self.client is not None

    def chat_json(self, messages: list[dict], schema_hint: str = "") -> dict | None:
        """请求 LLM 返回 JSON。失败返回 None（调用方降级模板）。"""
        if not self.client:
            return None
        try:
            resp = self.client.chat.completions.create(
                model=self.settings.llm_model,
                messages=messages,
                temperature=0.2,
                max_tokens=900,
                timeout=self.settings.llm_timeout_s,
            )
            text = resp.choices[0].message.content or ""
            text = text.strip()
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            return None
        except Exception:
            return None
