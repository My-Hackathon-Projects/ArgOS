# VC Brain — Sourcing

Challenge 02 (Maschmeyer Group × Hack-Nation). An AI-native VC operating system that runs the
funnel **Sourcing → Screening → Diligence → Decision**. This repo currently ships the **sourcing**
slice end-to-end: discover founders-to-be from their public footprint, resolve them to people, and
watch the signals stream into a live UI.

See `docs/SYSTEM_DESIGN.md` for the architecture and `CLAUDE.md` / `PRINCIPLES.md` for the rules.

---

## Architecture at a glance

| Piece | Where | Runs on |
|---|---|---|
| **Postgres + pgvector** (+ MinIO) | `docker-compose.yml` | `localhost:5433` (DB), `:9000/:9001` (MinIO) |
| **Sourcing backend** (FastAPI) — the live API | `backend/` | `localhost:8000` |
| **Frontend** (Next.js 16 + TS) | `frontend/` | `localhost:3000` |
| Diligence pipelines + template (WIP) | `BE/` | not wired to the frontend |

The frontend talks **only** to `backend/` (`:8000`). Types are generated from the backend's OpenAPI
schema, so the FE/BE contract is enforced by the compiler (see [Type-safe contract](#type-safe-febe-contract)).

---

## Prerequisites

- **Docker Desktop** (Postgres + pgvector)
- **[uv](https://docs.astral.sh/uv/)** (Python 3.12 backend)
- **Node ≥ 20.19** and npm (frontend) — Node 20.15 works but some deps warn
- **OpenAI + Tavily API keys** — only needed to *run discovery*; browsing existing/seeded data needs neither

---

## Run the full stack

From the repo root, in order:

### 1. Environment

```bash
cp .env.example .env          # PowerShell: copy .env.example .env
```

Fill in `OPENAI_API_KEY` and `TAVILY_API_KEY` (needed for discovery). One `.env` at the root serves
both backends; the frontend has its own `frontend/.env.local` (already set to `http://localhost:8000`).

### 2. Database

```bash
docker compose up -d          # Postgres+pgvector on :5433, MinIO on :9000/:9001
```

### 3. Sourcing backend (`:8000`)

```bash
cd backend
uv sync                                              # create .venv, install deps
uv run alembic upgrade head                          # apply migrations
uv run python -m uvicorn app.main:app --reload       # http://localhost:8000
```

Verify: <http://localhost:8000/health> → `{"status":"ok","signals":N}` · docs: <http://localhost:8000/docs>

### 4. Frontend (`:3000`)

```bash
cd frontend
npm install
npm run dev                                           # http://localhost:3000
```

Open <http://localhost:3000> — it redirects to **/sourcing**.

---

## Using the app

`/` → **/sourcing**. Left sidebar navigates the four views.

- **Sourcing** — a live **signal feed** (heartbeat header, new signals flash in on a 5s poll) plus
  the **"Monitoring"** panel of channels being watched, and a **Run discovery** button.
- **Founders** — table of everyone resolved from the feed → click a row for the **detail** view
  (identity links + signal timeline).
- **Thesis** — the active investment thesis (read-only for now).
- **Market Research** — aspirational preview, not yet wired to a backend.

### Populating the feed (sourcing)

Signals arrive via **discovery**: thesis → web search (Tavily) → founder resolution → persist.

- **From the UI:** click **Run discovery** on `/sourcing` (~30–60s; needs OpenAI + Tavily keys).
  New founders + signals are persisted and the feed animates them in.
- **From the CLI:**
  ```bash
  curl -X POST http://localhost:8000/discovery/run
  ```
- **Continuous polling** (APScheduler, `backend/app/scheduler.py`) is defined but **OFF by default**
  (not wired into `main.py`, jobs registered paused). Manual discovery is the supported path today.

Ingest a single signal directly (bypasses discovery):

```bash
curl -X POST http://localhost:8000/signals/ingest -H "Content-Type: application/json" \
  -d '{"source":"synthetic","signal_type":"post","external_id":"demo-1","title":"hello","summary":"a test signal"}'
```

### API surface (what the frontend wires)

| Method | Path | View |
|---|---|---|
| GET | `/health` | live heartbeat / signal count |
| GET | `/signals?limit=` | sourcing feed |
| POST | `/signals/ingest` | (manual ingest) |
| POST | `/discovery/run` | Run discovery button |
| GET | `/founders` | founders table |
| GET | `/founders/{id}` | founder detail |
| GET | `/sourcing-channels` | "Monitoring" panel |
| GET | `/thesis` | thesis view |

---

## Type-safe FE/BE contract

Pydantic `response_model`s are the source of truth. The flow:

```
backend Pydantic models → app.export_openapi → backend/openapi.json → orval → frontend TS types + TanStack Query hooks
```

Regenerate after any backend response-model change:

```bash
cd backend  && uv run python -m app.export_openapi   # refresh backend/openapi.json
cd frontend && npm run api:gen                        # regenerate typed client
npm run typecheck                                     # fails if the FE drifted from the API
```

`npm run typecheck` is the drift gate: a backend schema change that the frontend hasn't caught up
to becomes a TypeScript error.

---

## Test

**Backend**

```bash
cd backend
uv run pytest -q          # unit / contract tests
uv run ruff check .       # lint
uv run ruff format .      # format
```

**Frontend**

```bash
cd frontend
npm run typecheck         # tsc --noEmit — FE/BE type-sync gate
npm run lint              # eslint
```

**End-to-end smoke** (both servers up): load `/sourcing` (feed + channels render), open `/founders`,
click a founder (detail + timeline). Optionally hit **Run discovery** and watch new cards flash in.

---

## Troubleshooting

- **`WinError 10013` on `:8000`** — port taken by a leftover uvicorn. Use `--port 8001`, or find it:
  `Get-NetTCPConnection -LocalPort 8000`.
- **Port 3000 busy / kill the dev server** — `Get-NetTCPConnection -LocalPort 3000` then
  `Stop-Process -Id <pid> -Force`.
- **DB errors about `vector`** — you must use the `pgvector/pgvector` image (see `docker-compose.yml`);
  plain `postgres` fails the migrations.
- **Discovery returns nothing / errors** — check `OPENAI_API_KEY` and `TAVILY_API_KEY` in `.env`.
- **Disk full** — the Next `.next/` cache and Turbopack artifacts are regenerable; deleting
  `frontend/.next` frees space and rebuilds on next `npm run dev`.

---

## Repo layout

```
backend/     sourcing API (FastAPI) — the live backend on :8000
frontend/    Next.js app on :3000 (see frontend/README.md)
BE/          FastAPI template + diligence/validation LangGraph pipelines (not wired to FE yet)
docs/        SYSTEM_DESIGN.md, claims-layer.md, challenge brief
docker-compose.yml   Postgres+pgvector (:5433) + MinIO
.env.example         copy to .env (root) — serves both backends
```
