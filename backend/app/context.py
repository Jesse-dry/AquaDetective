"""共享运行时上下文：流域配置、DB 路径、LLM 客户端（懒加载单例）。"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .config import settings
from .data.watershed_builder import load_watershed

if TYPE_CHECKING:
    from .agents.llm import LLMClient

_watershed: dict | None = None
_llm: "LLMClient | None" = None


def get_db_path() -> str:
    return str(settings.db_path_abs)


def get_watershed() -> dict:
    global _watershed
    if _watershed is None:
        _watershed = load_watershed(settings.watershed_config_abs)
    return _watershed


def get_llm():
    global _llm
    if _llm is None:
        from .agents.llm import LLMClient
        _llm = LLMClient(settings)
    return _llm
