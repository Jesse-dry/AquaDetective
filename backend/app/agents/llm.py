"""LLM 客户端封装：OpenAI 兼容；不可用/失败时返回 None，由调用方走模板降级。

保证：演示现场无网/无 key 也能完成完整推理流程（模板推理）。
配置按 Agent 传入 profile 字典（见 Settings.llm_profile）：
未配置 `AQ_LLM_<AGENT>_*` 时，各 Agent 的 profile 与全局默认一致。
"""
from __future__ import annotations

import json
import logging

from ..config import Settings

logger = logging.getLogger(__name__)


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
            max_tokens = int(self.profile.get("max_tokens", 4096))
            resp = self.client.chat.completions.create(
                model=self.profile.get("model"),
                messages=messages,
                temperature=0.2,
                max_tokens=max_tokens,
                timeout=self.profile.get("timeout_s", 30.0),
            )
            choice = resp.choices[0]
            text = (choice.message.content or "").strip()
            if not text:
                # 推理模型把 token 全花在思维链上时,正文为空且 finish_reason=length。
                # 此前静默返回 None,用户只看到"和模板推理一样",无从查起。
                logger.warning(
                    "LLM 返回空内容(finish_reason=%s, max_tokens=%d, model=%s):"
                    "推理模型需要更大的 max_tokens,可调 AQ_LLM_MAX_TOKENS",
                    choice.finish_reason, max_tokens, self.profile.get("model"))
                return None
            if text.startswith("```"):
                text = text.strip("`")
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            if isinstance(data, dict):
                return data
            logger.warning("LLM 返回的不是 JSON 对象,降级模板推理: %s", text[:200])
            return None
        except Exception as e:
            logger.warning("LLM 调用失败,降级模板推理: %s: %s", type(e).__name__, e)
            return None
