from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at repo root (shared with docker-compose + frontend). Absolute path so
# it resolves no matter which directory the process is launched from.
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://vcbrain:vcbrain@localhost:5433/vcbrain"
    # Optional until the enrichment/LLM features land; real env vars override .env.
    openai_api_key: str | None = None
    tavily_api_key: str | None = None


settings = Settings()
