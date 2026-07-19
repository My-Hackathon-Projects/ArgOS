# Claims layer — what it is, how it fits signals + scoring

**Status:** `claim` + `claim_evidence` shipped (Alembic `0002`). Not built yet: the LLM
extraction/matching code, `score_history` (trend), and the company-level `opportunity_id`.

## Why claims exist

Raw `signal`s are noisy, duplicated, single-source events (a commit, a tweet, one reference to a
paper). A **claim** is the deduplicated, corroborated *assertion* derived from them — e.g.
"Published at NeurIPS 2024", "Shipped a product with 1k users". It is the unit the investor and
the scores reason about, and the unit that carries a **Trust Score**.

**One claim ← many signals.** Three references to the same paper (arXiv + the conference's own
page + a launch tweet) collapse into **one** claim with **high** trust — corroborated by several
high-authority sources.

Claims are the **seam between ingestion and scoring**: not every new signal is worth re-scoring a
founder, but every new or materially-changed claim is.

## The two tables

`claim` — one row per corroborated fact about a founder.
- `statement`, `category`, `attributes` — what it says (category also routes matching + memo section).
- `trust_score` + `trust_components` — the number and its receipts (deterministic; see below).
- `status` — `unverified | verified | contradicted | needs_review`.
- `dedup_key` — used to match a new signal to an existing claim.
- `updated_at` — bumps on evidence/trust change → **this is the rescore trigger**.

`claim_evidence` — `claim ↔ signal`, many-to-many.
- `stance` = `supports | refutes` (a `refutes` row **is** a contradiction).
- `weight` (source_reliability × recency × relevance), `extraction_conf`, `rationale`.
- Also the **provenance link** (claim → signal → `url`/`raw`) for agentic traceability.

## Signals → claims (extraction + matching)

On each new signal, decide **attach to an existing claim** (bump corroboration) vs **mint a new
claim**. This is entity-resolution-for-claims, done **incrementally** so cost stays bounded:

1. `dedup_key` exact hit → attach, no LLM.
2. else the founder's existing claims in the same `category` → candidate claims.
3. LLM adjudicates attach-vs-mint on just those candidates, and sets `stance`.

Never re-extract all of a founder's claims per signal — cost explodes as signals accumulate.

## Claims → scoring

Two numbers, both **deterministic formulas** over claim evidence. The LLM does the extraction and
judgment upstream; the numbers themselves stay auditable — that is the Trust criterion (an opaque
LLM confidence would lose it).

- **Trust Score (per claim)** = `f(Σ supports·weight, source authority, external_verified,
  − Σ refutes·weight)`. Stored on the claim (`trust_score` + `trust_components`).
- **Founder Score (per person, persistent)** = `Σ over the founder's claims (trust_score ×
  category_weight)`. A cheap aggregate — per-signal detail is already baked into each claim's trust.
  Recomputed when a claim is minted or its trust materially moves (watch `claim.updated_at`),
  **never** on every raw signal.

Expensive once (extraction), cheap forever (rescore) — that is exactly why the seam sits at the claim.

## The two loops (where claims plug in)

```
CONTINUOUS  (per new signal — cheap, always on):
  signal → resolve founder → match/mint claim (+evidence, +stance)
         → trust-score the claim (formula)
         → if new/changed: recompute Founder Score (+ trend)

TRIGGERED   (per opportunity: inbound application OR conviction threshold — expensive, occasional):
  screen → 3-axis (Founder axis uses Founder Score; Market/Idea need a company/idea)
         → memo (cites claims + their evidence) → recommendation + confidence
```

Claims feed **both** loops: the continuous loop builds the persistent Founder Score off them; the
triggered loop's 3-axis and memo read them (and their evidence citations).

## Contradictions

A signal that refutes a claim adds a `refutes` edge → lowers trust → sets
`status = contradicted` / `needs_review`. This is the brief's "flag contradictions before they
reach the investor."

## Shared seam — coordinate before changing

Both sides write `claim`:
- **Sourcing / continuous** (this side) mints **founder-level** claims from scraped signals.
- **Inbound / diligence** mints **company-level** claims (traction/revenue) from the deck; those
  carry `opportunity_id` (column lands with the opportunity table).

> **Landed in `0005`** (market-research seam): `claim.opportunity_id` (nullable FK) added and
> `claim.founder_id` made **nullable**, with CHECK `founder_id IS NOT NULL OR opportunity_id IS NOT
> NULL`. Company/market-level claims set `opportunity_id` + `founder_id NULL` so they never enter the
> Founder Score aggregation (which filters `founder_id = x`). Founder-claim writes are unchanged.
> The market agent (`app/market/`) is the first writer of opportunity-anchored claims. See
> `docs/market-layer.md`.

It is a shared contract: change the table in the open (edit this doc) and **chain the Alembic
revision** — `0002` is taken, next is `0003`. Don't both fork the same revision.

## Reconciliation with the validation pipeline (resolved 2026-07-19)

The separate `BE/` project (FastAPI template + LangGraph inbound/validation pipelines) has been
**removed**. Its genuinely new piece — inbound deck intake — was ported into
`backend/app/inbound/` (`POST /apply`: deck PDF -> per-page `signal` rows -> thesis pre-screen ->
opportunity-anchored `claim` rows with `claim_evidence` links, trust via the shared
`app.claims.trust` formula). Its validation-pipeline concepts were repository stubs that map onto
these tables natively: extracted claims = `claim` rows, trust verdicts = `claim.trust_score` +
`status`, contradictions = `claim_evidence WHERE stance='refutes'`. The diligence layer
(`opportunity`, `three_axis`, `memo`) already exists in `backend/` (migrations 0005/0006).
