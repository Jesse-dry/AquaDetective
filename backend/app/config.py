"""全局配置：环境变量前缀 AQ_，支持 .env 文件。"""
from __future__ import annotations

import os
from pathlib import Path
from typing import ClassVar, Literal

from dotenv import dotenv_values
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent

# .env 原始键值(pydantic 只解析已声明的字段,自定义的按 Agent 覆盖变量在此读取)
_ENV_FILE = dotenv_values(BASE_DIR / ".env")


def _env(key: str, default: str | None = None) -> str | None:
    """读取配置:真实环境变量优先,其次 .env 文件(与 pydantic-settings 行为一致)。"""
    return os.environ.get(key) or _ENV_FILE.get(key) or default


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AQ_", env_file=BASE_DIR / ".env", extra="ignore"
    )

    # 数据
    db_path: str = "data/aqua.db"
    seed: int = 20250601
    watershed_config: str = "app/data/watershed_config.json"

    # LLM（OpenAI 兼容）
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_timeout_s: float = 30.0
    allow_mock_llm: bool = True

    # 服务
    host: str = "127.0.0.1"
    port: int = 8000

    monitor_enabled: bool = True
    monitor_interval_s: int = Field(default=300, ge=10, le=86400)
    monitor_window_h: int = Field(default=24, ge=1, le=2160)
    monitor_method: Literal["cusum", "ewma", "threesigma", "seasonal"] = "seasonal"

    # 支持按 Agent 覆盖 LLM 配置的 Agent 名(与 graph.py 中节点分组一致)
    LLM_AGENTS: ClassVar[tuple[str, ...]] = (
        "investigator", "compliance", "responder", "reporter")

    def llm_profile(self, agent: str | None = None) -> dict:
        """返回某 Agent 的 LLM 配置:全局默认 + `AQ_LLM_<AGENT>_*` 覆盖。

        agent=None 返回全局默认;传入 agent 名(如 "reporter")时,
        用 AQ_LLM_REPORTER_API_KEY / _BASE_URL / _MODEL / _TIMEOUT_S 覆盖对应字段。
        未配置任何覆盖项时,返回结果与全局默认完全一致(即维持现状)。
        """
        profile: dict = {
            "base_url": self.llm_base_url,
            "api_key": self.llm_api_key,
            "model": self.llm_model,
            "timeout_s": self.llm_timeout_s,
        }
        if not agent:
            return profile
        prefix = f"AQ_LLM_{agent.upper()}_"
        for env_key, field in (("API_KEY", "api_key"), ("BASE_URL", "base_url"),
                               ("MODEL", "model"), ("TIMEOUT_S", "timeout_s")):
            val = _env(prefix + env_key)
            if val:
                profile[field] = float(val) if field == "timeout_s" else val
        return profile

    @property
    def db_path_abs(self) -> Path:
        p = Path(self.db_path)
        return p if p.is_absolute() else BASE_DIR / p

    @property
    def watershed_config_abs(self) -> Path:
        p = Path(self.watershed_config)
        return p if p.is_absolute() else BASE_DIR / p

    def ensure_dirs(self) -> None:
        self.db_path_abs.parent.mkdir(parents=True, exist_ok=True)
        (BASE_DIR / "data" / "recordings").mkdir(parents=True, exist_ok=True)


settings = Settings()
