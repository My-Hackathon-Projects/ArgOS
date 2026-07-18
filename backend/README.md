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

Ingest a test signal:

```bash
curl -X POST http://localhost:8000/signals/ingest -H "Content-Type: application/json" \
  -d '{"source":"synthetic","signal_type":"post","external_id":"1","title":"hello"}'
```

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
  config.py            settings (DATABASE_URL from .env)
  db.py                engine, session, Base
  models.py            Founder, Identity, Signal, JobRun  (scraping-core schema)
  ingest.py            upsert_signal() — idempotent ON CONFLICT dedupe
  connectors/base.py   SignalEnvelope + Connector ABC  (the source contract)
  main.py              FastAPI app
alembic/               migrations (0001 = initial scraping schema)
tests/                 pure-unit contract tests (no DB)
../docker-compose.yml  pgvector/pgvector:pg16  (at repo root)
```

## Add a source connector

Subclass `Connector` (`app/connectors/base.py`), implement `fetch()` + `normalize(raw) -> SignalEnvelope`, feed envelopes to `upsert_signal()`. No schema change needed.
