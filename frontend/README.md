# VC Brain — Frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4. The UI for the sourcing slice, wired to the
FastAPI backend at `backend/` (`http://localhost:8000`).

For full-stack setup (DB + backend + this app), see the root [`README.md`](../README.md). This file
covers the frontend only.

## Stack

- **Next.js 16** (App Router, Turbopack) · **React 19** · **TypeScript**
- **Tailwind v4** — theme tokens live in `src/app/globals.css` (`:root` + `@theme`); reskin by editing them
- **TanStack Query** + **orval** — typed API client generated from the backend OpenAPI schema
- **motion** (Framer Motion) — feed animations (heartbeat header, signal fly-in)
- **lucide-react** — icons

## Run

```bash
npm install
npm run dev        # http://localhost:3000  (redirects to /sourcing)
```

Requires the backend running on `:8000`. The API base URL is read from `frontend/.env.local`:

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Scripts

| Script | What |
|---|---|
| `npm run dev` | dev server (Turbopack) on :3000 |
| `npm run build` / `start` | production build / serve |
| `npm run typecheck` | `tsc --noEmit` — the FE/BE **type-sync gate** |
| `npm run api:gen` | regenerate the typed client from `../backend/openapi.json` |
| `npm run lint` | eslint |

## Data layer (typed, generated)

Never hand-write API types. They are generated from the backend's OpenAPI schema:

```
backend Pydantic models → backend/openapi.json → orval → src/api/generated/**
```

- `orval.config.ts` — codegen config (react-query client, axios http, custom mutator)
- `src/api/axios-instance.ts` — the axios mutator (base URL, unwraps response body)
- `src/api/generated/` — **generated**, committed; do not edit by hand

Regenerate after a backend response-model change:

```bash
cd ../backend && uv run python -m app.export_openapi   # refresh the schema
cd ../frontend && npm run api:gen && npm run typecheck  # regen client + catch drift
```

Use a hook by importing from the generated module, e.g.:

```ts
import { useListSignals, useGetFounder } from "@/api/generated/default/default";
```

## Layout

```
src/
  app/
    layout.tsx              root layout: fonts, Providers, AppShell
    providers.tsx           TanStack QueryClientProvider
    globals.css             design tokens + animations (heartbeat/flash)
    sourcing/               live signal feed + channels + discovery
    founders/               table + [id] detail
    settings/               thesis (read-only)
    research/               market-research preview (not wired)
  components/
    app-shell.tsx           sidebar nav
    sourcing/               live-header, signal-feed, signal-card, channel-list, discovery-button
    founders/               founders-table, founder-detail
    settings/               thesis-view
    ui/                      button, card, badge, skeleton, page-header
  lib/                      utils (cn), format (time/initials), source-style (gradients)
  api/                      axios instance + generated client
```
