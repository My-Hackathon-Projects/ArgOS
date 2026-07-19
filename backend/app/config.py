from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at repo root (shared with docker-compose + frontend).
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
# Populate os.environ so libs that read env directly (LangSmith tracing) pick up the keys.
load_dotenv(ROOT_ENV)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://vcbrain:vcbrain@localhost:5433/vcbrain"

    openai_api_key: str | None = None
    tavily_api_key: str | None = None

    # Models — mini-only for now (both tiers point at mini).
    model_fast: str = "gpt-5.4-mini"
    model_smart: str = "gpt-5.4-mini"

    # Discovery caps (Q7 — bounded autonomy, all tunable).
    max_search_queries: int = 4
    tavily_max_results: int = 4
    max_candidates: int = 3
    max_extracts: int = 24


settings = Settings()
