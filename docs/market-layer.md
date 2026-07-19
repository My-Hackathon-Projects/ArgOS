# Market-research layer — what it produces, which tables, how it feeds 3-axis + memo

**Status:** shipped (`backend/app/market/`, Alembic `0005`). The external background-research desk of
the diligence loop. Reuses the sourcing web utils (tavily client, URL canonicalization, per-source
reliability) and the claims-layer trust formula (`app/claims/trust.py`) — **no parallel models**.

## What it is

Given an **opportunity** (founder + idea/sector, company optional), it web-researches the *outside
world* a VC checks before a term sheet and fills the memo's numbers. It does **not** own the deck's
internal company facts (that's the inbound/claims side); it may read a startup's stated KPIs to
benchmark them, never to produce them.

**Precondition:** runs only when the opportunity has an **idea/sector**. A pre-idea founder has no
market to size (tracked at the founder level instead).

## What it produces (→ memo sections)

| Memo section | Contribution |
|---|---|
| Market sizing | TAM / SAM / SOM + method + assumptions, CAGR, maturity |
| Competition | competitor clusters, positioning, concentration, emerging threats |
| Comparables | problem-similar startups that **raised** (round/stage/valuation/investors) |
| Traction & KPIs | sector benchmarks: CAC, CPC, LTV, gross margin, ACV, seed round size |
| Investment hypotheses | market bull hypotheses + the bear counter-case |
| SWOT | the Opportunities + Threats halves |
| Problem & product | "why now" / demand + timing |

Plus the **Market axis** of the 3-axis screen.

## The graph (`graph.py`, mirrors `sourcing/`)

```
plan_research (fast)  → Tavily queries TAGGED by sub-goal {sizing,competition,comparables,kpi,trend}
run_searches          → shared tagged pool, ThreadPool; each hit tagged; comps biased to funding-news
extract (parallel)    → extract_sizing / extract_competition / extract_comparables / extract_kpi
synthesize (smart)    → hypotheses + SWOT O/T + why-now, THEN the Market axis {verdict,score,trend}
finalize              → in-memory MarketAnalysis; persist is a separate single-writer step
```

- **Prompts** (`prompts.py`) are XML-tag-structured (`<role>/<opportunity>/<thesis>/<evidence>/
  <task>/<rules>`). Thesis rides in every prompt → the Market axis is scored **thesis-relative**.
- **Anti-fabrication:** every `Figure` carries a `basis` of `reported | estimated_bottom_up | gap`.
  Reported cites its source; bottom-up cites its inputs + records the derivation; a gap is
  flagged, never invented (a flagged gap scores higher than a fake number — eval's honesty criterion).

## Tables it writes (Alembic `0005`)

- **`opportunity`** — the deal: `founder_id` + optional `company_id` + `idea/sector/geo`. Idea-stage
  deals have `company_id NULL`. (`company`, `founder_company` created alongside; company optional.)
- **`three_axis`** — the `axis='market'` row: `verdict` (bull/neutral/bear), `score` 0..100
  (thesis-relative), `trend` (improving/declining/stable — a market-momentum proxy), `rationale`,
  `confidence`, `evidence` (cited claim_ids + urls), `gaps`. Upsert on `(opportunity_id, axis)`.
- **`claim`** (category `market_size|competition|comparable|market`) — **opportunity-anchored**
  (`opportunity_id` set, `founder_id NULL`). `founder_id` NULL is deliberate: Founder Score sums
  claims WHERE `founder_id = x`, so market claims must never carry one.
- **`claim_evidence`** (`stance='supports'`) — one edge per cited source signal.
- **`signal`** (`source='web'`, `founder_id NULL`) — one per cited URL. NULL founder keeps them out
  of the founder-claim extractor.

## Trust — reused, not forked

Each market claim's `trust_score` / `status` / `trust_components` come from **`app/claims/trust.py`**
(noisy-OR over evidence weights) — the identical deterministic formula founder claims use. A
single-source web figure lands ~unverified; cross-source corroboration lifts it. `trust_score` is
`NULL` only if the shared function is unavailable — never a parallel implementation.

## Provenance / end-to-end traceability

Every number traces to a source: extractor `citation_indices` → the hit it was given → a `web`
`signal` → its `url`/`raw`. `three_axis.evidence = {claim_ids, urls}` and each claim's
`claim_evidence` rows point at the backing signals. So the memo's Market axis drills:
**axis → claims → evidence → signal → source url**. A figure/competitor/comparable with no
resolvable citation is dropped (the claims-layer anti-hallucination rule).

## How to run

```bash
# demo (no DB) — prints TAM/SAM/SOM + competitors + comparables + market axis, all cited:
uv run python -m app.market.run

# service (persists against the live DB):
from app.market.service import run_market_analysis
run_market_analysis(db, {"founder_id": ..., "company_name": ..., "idea": ..., "sector": ..., "geo": ...})
# or re-run an existing opportunity:  run_market_analysis(db, opportunity_id=<id>)
```

Idempotent: re-runs upsert the `three_axis` row and dedup claims on `(opportunity_id, dedup_key)`.

## Shared-seam changes (announced)

`0005` is additive but touches the shared `claim` table — coordinate before changing:
- `claim.founder_id` made **nullable**; new `claim.opportunity_id` (nullable FK); CHECK
  `founder_id IS NOT NULL OR opportunity_id IS NOT NULL`. Confirms claims-layer.md's `opportunity_id`
  direction — founder-claim writes are unaffected (they still set `founder_id`).
- New `opportunity` / `company` / `founder_company` / `three_axis` (see SYSTEM_DESIGN §4).
