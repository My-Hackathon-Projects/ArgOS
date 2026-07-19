from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env lives at repo root (shared with docker-compose + frontend).
ROOT_ENV = Path(__file__).resolve().parents[2] / ".env"
# Populate os.environ so libs that read env directly (LangSmith tracing) pick up the keys.
load_dotenv(ROOT_ENV)


def parse_cors_origins(value: str | None) -> list[str]:
    if not value:
        return []
    return [origin.strip().rstrip("/") for origin in value.split(",") if origin.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT_ENV, extra="ignore")

    database_url: str = "postgresql+psycopg://vcbrain:vcbrain@localhost:5433/vcbrain"

    openai_api_key: str | None = None
    tavily_api_key: str | None = None
    # Optional — native GitHub fetcher works keyless (10 req/min); token raises to 30.
    github_token: str | None = None

    # Comma-separated browser origins allowed to call the API.
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Models — mini for high-volume (plan/screen), full 5.4 for per-founder synthesis.
    model_fast: str = "gpt-5.4-mini"
    model_smart: str = "gpt-5.4"

    # Discovery caps (Q7 — bounded autonomy, all tunable).
    queries_per_channel: int = 3  # 13 channels → ~39 queries/run
    max_search_queries: int = 40
    tavily_max_results: int = 8
    native_max_results: int = 10  # per-query cap for native fetchers (github/arxiv/hn)
    max_candidates: int = 35
    max_extracts: int = 300
    hit_content_chars: int = 3500  # per-hit content fed to screening (advanced search + raw)
    extract_chunk_size: int = 12  # hits per screening LLM call (chunked + parallel)
    research_rounds: int = 3  # recursive per-founder search rounds
    max_workers: int = 16  # parallel Tavily / LLM calls

    # Network-hop expansion: mine researched founders' orbits (co-authors, teammates,
    # co-founders) as NEW candidates — one bounded recursive hop per run.
    hop_enabled: bool = True
    hop_max_candidates: int = 10

    # Sourcing cron (active by default; modest cadence — env-tunable).
    cron_enabled: bool = True
    discovery_interval_min: int = 60  # discovery: hourly
    refresh_interval_min: int = 360  # refresh: every 6h (stalest founders first)
    claims_interval_min: int = 15  # claims/scoring: every 15min (cheap when nothing changed)

    # Market-research agent caps (bounded, tunable).
    market_queries_per_goal: int = 2  # 5 sub-goals -> ~10 queries/run
    market_max_results: int = 6  # Tavily results per query
    market_max_hits_per_goal: int = 10  # cap evidence fed to each extractor LLM

    @property
    def cors_origin_list(self) -> list[str]:
        return parse_cors_origins(self.cors_origins)


settings = Settings()
