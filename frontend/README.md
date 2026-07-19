# ArgOS — Frontend

Next.js 16 (App Router) + TypeScript + Tailwind v4. The UI for ArgOS's home, sourcing,
inbound, founders, thesis, decisions, and market research flows, wired to the FastAPI backend at `backend/`
(`http://localhost:8000`).

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
npm run dev        # http://localhost:3000  (home page)
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
| `npm run typecheck` | `next typegen && tsc --noEmit` — route types plus the FE/BE **type-sync gate** |
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
    layout.tsx              root layout: Providers, NavBar, Footer (system font stack, no webfonts)
    template.tsx            page-entry transition (remounts per navigation)
    providers.tsx           TanStack QueryClientProvider
    globals.css             design tokens (Apple-style light theme) + animations
    page.tsx                home: convergence hero, funnel cards, About Us team section
    sourcing/               live signal feed + search + type filters + channels + discovery
    inbound/                applications inbox + new-application form
    founders/               searchable/sortable table + [id] detail (claims, Founder Score)
    opportunities/          Decisions UI: list + [id] detail (three-axis screen, market analysis, memo)
    settings/               thesis (read-only)
    research/               redirect to /opportunities (old URL kept working)
  components/
    shell/                  nav-bar (sticky top nav with Thesis on the right), footer
    home/                   convergence-hero, team-section (photos from public/images)
    sourcing/               live-header, signal-feed, signal-card, type-filter, channel-list,
                            discovery-button
    inbound/                inbound-view (email-style inbox rows over /opportunities)
    founders/               founders-table, founder-toolbar, sort, founder-detail,
                            claims-list, timeline-item, status
    opportunities/          Decisions page components: opportunities-list, opportunity-detail,
                            memo-section (generate/read memo), axis (chips + score cards)
    market/                 market-analysis (embedded in opportunity detail) + axis-card,
                            figure-card, entity-cards, gaps-card, section, meta
    settings/               thesis-view
    ui/                      button, card, badge, skeleton, page-header, container,
                            pagination (PAGE_SIZE = 10), filter-pills, search-input
  lib/                      utils (cn), format (time/initials), source-style (colors/logos)
  api/                      axios instance + generated client
public/images/              team profile photos (wired in home/team-section.tsx)
```

All pages are responsive: the nav collapses to a hamburger sheet below `md`, the founders
table becomes stacked cards, and figure grids go 4 to 2 to 1 columns. Long lists (signal feed,
founders, founder timelines) paginate client-side at 10 per page. The founders table header and
rows share one fixed-width grid template (`GRID` in `founders-table.tsx`); keep them identical or
the headings drift off the columns.
