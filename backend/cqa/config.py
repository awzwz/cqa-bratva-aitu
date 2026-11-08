"""Runtime configuration. Everything comes from environment variables (12-factor);
the same image runs as `api`, `worker` or `all` depending on SERVICE."""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]  # repository root (…/cqa)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CQA_", env_file=(ROOT / ".env"), extra="ignore")

    service: str = Field("all", description="api | worker | all")
    database_url: str = Field(f"sqlite:///{ROOT / 'data' / 'cqa.db'}", description="SQLAlchemy URL; PostgreSQL in compose/k8s")
    redis_url: str | None = Field(None, description="redis://… enables the Redis Streams queue; None = in-process queue")
    data_dir: Path = ROOT / "data"
    results_dir: Path = ROOT / "results"
    team_name: str = "Bratva Aitu"

    # organisers' Power Automate endpoint (signed URL; group_id is added by code)
    org_api_url: str | None = None
    org_api_timeout: float = 130.0
    org_api_retries: int = 3

    # LLM providers — chain order is the fallback order
    provider_chain: str = Field("openai", description="comma-separated: openai,anthropic,gemini,deepseek,ollama,lmstudio")
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.5"
    openai_base_url: str | None = None
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-5-5"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.8-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta/openai"
    deepseek_api_key: str | None = None
    deepseek_model: str = "deepseek-chat"
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_model: str = "qwen3.5:9b"
    lmstudio_base_url: str = "http://127.0.0.1:1234/v1"
    lmstudio_model: str = "local-model"
    second_opinion_provider: str | None = Field(None, description="provider id used for the local second opinion, e.g. ollama")

    llm_timeout: float = 90.0
    llm_parallel: int = 4
    llm_budget_usd: float = 5.0
    mask_pii: bool = True

    cors_origins: str = "*"
    log_level: str = "INFO"


settings = Settings()
settings.data_dir.mkdir(parents=True, exist_ok=True)
(settings.results_dir / "dev").mkdir(parents=True, exist_ok=True)
(settings.results_dir / "prod").mkdir(parents=True, exist_ok=True)
