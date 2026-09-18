"""共享运行时上下文：流域配置、DB 路径、LLM 客户端（懒加载单例）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .config import settings
from .data.watershed_builder import load_watershed

if TYPE_CHECKING:
    from .agents.llm import LLMClient

_watershed: dict | None = None
_llm_cache: dict[str, "LLMClient"] = {}


def get_db_path() -> str:
    return str(settings.db_path_abs)


def get_watershed() -> dict:
    global _watershed
    if _watershed is None:
        _watershed = load_watershed(settings.watershed_config_abs)
    return _watershed


def get_llm(agent: str | None = None):
    """取 LLM 客户端(按 Agent 缓存)。

    agent=None 返回全局默认客户端;传入 agent 名(investigator / compliance /
    responder / reporter)时,使用 `AQ_LLM_<AGENT>_*` 覆盖后的配置。
    未配置任何覆盖项时,各 Agent 拿到的配置与全局默认完全一致。
    """
    key = agent or "_default"
    if key not in _llm_cache:
        from .agents.llm import LLMClient
        _llm_cache[key] = LLMClient(settings.llm_profile(agent))
    return _llm_cache[key]
