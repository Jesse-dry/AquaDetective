"""LLM 客户端封装：OpenAI 兼容；不可用/失败时返回 None，由调用方走模板降级。

保证：演示现场无网/无 key 也能完成完整推理流程（模板推理）。
配置按 Agent 传入 profile 字典（见 Settings.llm_profile）：
未配置 `AQ_LLM_<AGENT>_*` 时，各 Agent 的 profile 与全局默认一致。
"""
from __future__ import annotations

import json

from ..config import Settings


class LLMClient:
    def __init__(self, profile: dict | Settings):
        # 兼容两种入参:profile 字典(推荐)或旧的 Settings 对象
        if isinstance(profile, Settings):
            profile = profile.llm_profile()
        self.profile = profile
        self.client = None
        api_key = profile.get("api_key")
        if api_key:
            try:
                from openai import OpenAI
                kwargs: dict = {"api_key": api_key}
                if profile.get("base_url"):
                    kwargs["base_url"] = profile["base_url"]
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
                model=self.profile.get("model"),
                messages=messages,
                temperature=0.2,
                max_tokens=900,
                timeout=self.profile.get("timeout_s", 30.0),
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
