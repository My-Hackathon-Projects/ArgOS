# VC Brain — Backend (Sourcing / Signal Ingestion)

Challenge 02. Python + FastAPI, Postgres (pgvector), SQLAlchemy 2.0 + Alembic, managed with `uv`.

## Quick start

Only **Postgres runs in Docker**; the **FastAPI app runs on your host** with hot-reload (it talks to the DB at `localhost:5433`). `.env` and `docker-compose.yml` live at the **repo root** (shared with the future frontend).

```bash
# from repo root
cp .env.example .env                      # PowerShell: copy .env.example .env  (fill in keys)
docker compose up -d                      # Postgres + pgvector on :5433

cd backend
uv sync                                    # create .venv, install deps
uv run alembic upgrade head                # apply migrations
uv run python -m uvicorn app.main:app --reload   # http://localhost:8000
```

Verify: <http://localhost:8000/health> → `{"status":"ok","signals":0}`

CI (`.github/workflows/backend.yml`, on backend changes): ruff lint + format check, then alembic migrations + pytest against a pgvector service container on :5433 — same setup as local, so `uv run pytest -q` locally predicts CI.

Ingest a test signal:

```bash
curl -X POST http://localhost:8000/signals/ingest -H "Content-Type: application/json" \
  -d '{"source":"synthetic","signal_type":"post","external_id":"1","title":"hello"}'
```

## Sourcing / discovery

Discovery is thesis → web search (Tavily) → founder resolution → persist. Needs
`OPENAI_API_KEY` + `TAVILY_API_KEY` in the root `.env`.

```bash
curl -X POST http://localhost:8000/discovery/run     # ~30-60s; persists founders + signals
```

APScheduler jobs exist in `app/scheduler.py` but are **OFF by default** (not wired into `main.py`).
Manual discovery is the supported path today.

Endpoints: `/health` · `/signals` · `/signals/ingest` · `/discovery/run` · `/founders` ·
`/founders/{id}` · `/sourcing-channels` · `/thesis`. Full schema at `/docs`.

## OpenAPI export (frontend contract)

Endpoints declare Pydantic `response_model`s (`app/api_schemas.py`) so the schema is fully typed.
The frontend generates its client from it; regenerate the file after any response-model change:

```bash
uv run python -m app.export_openapi     # writes backend/openapi.json (the FE/BE contract)
```

CORS is enabled for the Next.js dev origin (`localhost:3000`) in `app/main.py`.

## Run the app (day-to-day)

Leave the DB container up; you only restart the app. **Run from `backend/`** so `app.main` resolves and it uses `backend/.venv`:

```bash
cd backend
uv run python -m uvicorn app.main:app --reload
```

- API <http://localhost:8000> · interactive docs <http://localhost:8000/docs> · health <http://localhost:8000/health>
- `--reload` restarts on save; stop with Ctrl+C.
- **Windows `WinError 10013`** = port 8000 already taken (usually a leftover uvicorn). Use another port `--port 8001`, or find/kill the holder: `Get-NetTCPConnection -LocalPort 8000`.

## Dev checks

```bash
uv run ruff check .        # lint
uv run ruff format .       # format
uv run pytest -q           # tests
```

## Migrations (Alembic = versioned DB schema)

```bash
uv run alembic revision --autogenerate -m "describe change"   # diff models → new migration
uv run alembic upgrade head                                    # apply
uv run alembic downgrade -1                                     # roll back one
```

## Layout

```
app/
  config.py            settings (DATABASE_URL + OpenAI/Tavily keys from .env)
  db.py                engine, session, Base
  models.py            Founder, Identity, Signal, JobRun, Claim, ClaimEvidence,
                       InvestmentThesis, SourcingChannel
  ingest.py            upsert_signal() — idempotent ON CONFLICT dedupe
  connectors/base.py   SignalEnvelope + Connector ABC  (the source contract)
  sourcing/            discovery graph, thesis, persistence, seed reference data
  api_schemas.py       Pydantic response_models  (the FE/BE wire contract)
  export_openapi.py    dump backend/openapi.json for frontend codegen
  scheduler.py         APScheduler jobs (OFF by default)
  main.py              FastAPI app (+ CORS for localhost:3000)
alembic/               migrations
tests/                 pure-unit contract tests (no DB)
../docker-compose.yml  pgvector/pgvector:pg16  (at repo root)
```

## Add a source connector

Subclass `Connector` (`app/connectors/base.py`), implement `fetch()` + `normalize(raw) -> SignalEnvelope`, feed envelopes to `upsert_signal()`. No schema change needed.
