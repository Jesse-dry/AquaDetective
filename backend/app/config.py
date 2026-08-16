"""全局配置：环境变量前缀 AQ_，支持 .env 文件。"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


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
