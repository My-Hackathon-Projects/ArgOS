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
    queries_per_channel: int = 2  # 13 channels → ~26 queries/run
    max_search_queries: int = 26
    tavily_max_results: int = 8
    max_candidates: int = 25
    max_extracts: int = 200
    hit_content_chars: int = 3500  # per-hit content fed to screening (advanced search + raw)
    extract_chunk_size: int = 12  # hits per screening LLM call (chunked + parallel)
    research_rounds: int = 3  # recursive per-founder search rounds
    max_workers: int = 12  # parallel Tavily / LLM calls

    # Market-research agent caps (bounded, tunable).
    market_queries_per_goal: int = 2  # 5 sub-goals -> ~10 queries/run
    market_max_results: int = 6  # Tavily results per query
    market_max_hits_per_goal: int = 10  # cap evidence fed to each extractor LLM


settings = Settings()
