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

    # Models — mini for high-volume (plan/screen), full 5.4 for per-founder synthesis.
    model_fast: str = "gpt-5.4-mini"
    model_smart: str = "gpt-5.4"

    # Discovery caps (Q7 — bounded autonomy, all tunable).
    queries_per_channel: int = 2
    max_search_queries: int = 16
    tavily_max_results: int = 6
    max_candidates: int = 12
    max_extracts: int = 60
    research_rounds: int = 2  # recursive per-founder search rounds
    max_workers: int = 8  # parallel Tavily / LLM calls


settings = Settings()
