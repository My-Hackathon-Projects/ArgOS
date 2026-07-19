# VC Brain — Requirements & LangGraph Specification (3-Graph Architecture)

> **Audience:** this README is the implementation brief for Claude Code.
> It is the source of truth for WHAT to build. Where it conflicts with
> intuition, this document wins. Stack: Python 3.11+, LangGraph, LangChain
> (structured output), Postgres (+pgvector), FastAPI, LangSmith tracing.

---

## 1. Challenge TL;DR (what we are graded on)

We are building an AI-first VC operating system covering
**Sourcing → Screening → Diligence → Decision**: it must justify a $100K
invest/pass recommendation on a startup within 24 hours, with exactly one
human approval step. Downstream stages (portfolio monitoring, follow-on,
fund ops, exit) are **out of scope — do not build them**.

**Evaluation weights:**

| Criterion | Weight | What it means for the code |
|---|---|---|
| Data Architecture & Intelligence | 30% | Smart ingestion, dedup, enrichment, append-only Memory. **Must explicitly handle the cold-start founder (no GitHub, no funding, no network) or this scores poorly.** |
| Investment Utility & Execution | 30% | A recommendation an investor can act on fast. **Instrument time-to-decision** (timestamps at every pipeline stage, surfaced in the API). |
| Intelligent Analysis & Trust | 25% | Per-claim Trust Scores, evidence + uncertainty surfaced transparently, contradictions flagged. |
| UX & Design | 15% | Not this repo's concern beyond clean JSON view models. |

**Hard rules (graded tripwires — enforce in code, not just prompts):**

1. **Never average the three axis scores.** Founder / Market / Idea-vs-Market
   are independent scores, each with a trend (improving/stable/declining).
2. **Trust Score is per claim**, not per company: every claim carries
   `{status: verified|unverified|contradicted, confidence, evidence_ids}`.
3. **Founder Score is per person, persists forever, never resets.** It is
   one *input* to the Founder axis, not a substitute for it.
4. **Never fabricate missing data.** Memo gaps are flagged explicitly
   ("Cap table: not disclosed"), never silently omitted or invented.
5. **Nothing discarded.** Signals are append-only; rejections are logged
   with reasons, not deleted.
6. **Both intake tracks converge into ONE funnel** — outbound candidates are
   scored exactly like inbound applications.
7. **Cold outreach, not cold investment** — outbound generates outreach
   drafts whose goal is to trigger a real application. We never auto-invest
   from a scan.
8. Memo required sections: Company snapshot, Investment hypotheses, SWOT,
   Problem & product, Traction & KPIs. Padding counts against us.
9. Minimum inbound application = company name + deck PDF. Do not require
   more fields.
10. One human in the loop: a single interrupt before the final decision.

---

## 2. Architecture: THREE graphs, one database

We run **three separate LangGraph graphs**. Inbound and Outbound are intake
graphs; both terminate by handing off to the Processing graph. All three
share one Postgres (domain tables + LangGraph checkpoints) and one contract
module (`models.py`).

```
┌─────────────────────┐      ┌──────────────────────────┐
│  GRAPH 1: INBOUND    │      │  GRAPH 2: OUTBOUND        │
│  trigger: POST /apply│      │  trigger: cron + manual   │
│  deck → signals →    │      │  scan channels → deep     │
│  entities → claims → │      │  research → entities →    │
│  pre-screen          │      │  quick-score → outreach   │
└─────────┬───────────┘      └───────────┬──────────────┘
          │ pass                          │ above threshold
          ▼                               ▼
        HANDOFF: ProcessingTicket (shared contract, §5)
                          │
                          ▼
┌──────────────────────────────────────────────────────┐
│  GRAPH 3: PROCESSING ("the VC brain")                 │
│  3-axis scoring (parallel) → validator loop →         │
│  memo generation → interrupt (human) → writeback      │
└──────────────────────────────────────────────────────┘
```

Why three graphs (design rationale — preserve these properties):

- **Different triggers/lifecycles:** inbound is request-driven (seconds),
  outbound is scheduled (cron, minutes, can be slow), processing is
  long-running with a human pause. A slow web-research crawl must never
  block a live application.
- **Independent failure/retry:** each graph has its own checkpointer
  threads; a crashed scan never corrupts a processing run.
- **One funnel is preserved at the data level:** both intake graphs emit the
  same `ProcessingTicket`, so Processing cannot even tell tracks apart
  except by the `track` field.

**Thread-id convention (correlation key everywhere):**

- Inbound graph: `thread_id = f"in:{opportunity_id}"`
- Outbound graph: `thread_id = f"out:{scan_id}"` (one thread per scan run)
- Processing graph: `thread_id = opportunity_id` — also the key joining API
  routes, checkpoints, domain rows, and LangSmith traces.

---

## 3. GRAPH 1 — INBOUND (sourcing + screening of an applicant)

**Trigger:** `POST /apply` (multipart: `company_name` + deck PDF). API
returns `{opportunity_id, status:"running"}` in <1s; graph runs as a
background task.

**State — `InboundState(TypedDict)`:**

```
opportunity_id: str
thesis: Thesis
raw_deck: bytes | storage-ref
company_name: str
signals: list[Signal]            # append-only observations
founder: Founder | None
company: Company | None
claims: list[Claim]              # trust=None at this stage
prescreen: PreScreenResult | None
ticket: ProcessingTicket | None
stage_timestamps: dict[str, str]
```

**Nodes (in order):**

| Node | Does | Reads/Writes DB | LLM |
|---|---|---|---|
| `ingest_deck` | pymupdf per-page text extraction → one `Signal` per page (`source_pointer="deck p.N"` preserved) + application-form Signal | writes `signals` | none |
| `resolve_entities` | entity resolution: exact handle match → fuzzy name → pgvector similarity; on match, MERGE into canonical Founder (Founder Score history carries over); else create | reads/writes `entities` | none |
| `extract_claims` | structured extraction of Claims (category ∈ traction/revenue/team/market, text, source_pointer). Born with `trust=None` | writes `claims` | fast, `with_structured_output(list[Claim])` |
| `pre_screen` | cheap kill-filter: (a) deterministic thesis hard filters (sector/geo/stage) in code, (b) one fast-LLM viability check. Reject ⇒ reason logged | writes rejection log | fast |
| `emit_ticket` | build `ProcessingTicket`, persist Opportunity row (stage="screened"), invoke Processing graph (async) | writes `opportunities` | none |

**Edges:**

```
START → ingest_deck → resolve_entities → extract_claims → pre_screen
pre_screen —route_prescreen→ { "pass": emit_ticket, "reject": END }
emit_ticket → END
```

**Acceptance criteria:**
- Deck upload → ticket emitted in < 60s on the seed data.
- Re-uploading the same deck does not duplicate signals/entities (idempotent).
- A rejected application has a queryable rejection reason; its signals remain
  in Memory and still feed the Founder Score.

---

## 4. GRAPH 2 — OUTBOUND (scheduled scanning + deep research + activation)

**Trigger:** APScheduler cron (every N minutes, configurable) AND a manual
`POST /scan` for demos. Input: the active `Thesis` (queries are derived from
its sectors/geo/stage — never hardcoded).

**State — `OutboundState(TypedDict)`:**

```
scan_id: str
thesis: Thesis
channel_queries: dict[str, list[str]]   # generated from thesis
raw_signals: list[Signal]
candidates: list[CandidateProfile]      # grouped per person after resolution
research_notes: dict[founder_id, ResearchDossier]
quick_scores: dict[founder_id, QuickScore]
activated: list[OutreachDraft]
stage_timestamps: dict[str, str]
```

**Nodes:**

| Node | Does | LLM |
|---|---|---|
| `plan_queries` | derive channel-specific search queries from the Thesis (e.g. sectors → GitHub topics, arXiv categories, HN keywords) | fast |
| `scan_channels` | fan out (parallel) over GitHub API, HN Algolia, arXiv; everything returned becomes an append-only `Signal` with `entity_hints`; idempotent on source_url | none |
| `resolve_candidates` | group signals into `CandidateProfile`s via the same entity-resolution helpers as inbound (shared code, not copied) | none |
| `deep_research` | **the deep-web-research agent — the ONE open-ended agent in the system.** For each top candidate: ReAct-style loop with tools {web/API search, fetch page, GitHub profile/repos} that follows links (pinned site → docs → launch post), decides what's missing, searches again. Hard budget: ≤ N tool calls / ≤ T seconds per candidate. Output: `ResearchDossier` (structured), every fetched artifact ALSO saved as a Signal | strong, ReAct agent |
| `quick_score` | thin scoring pass through the thesis lens → `QuickScore {score, confidence, rationale}`. NOT the 3-axis score (that is Processing's job) — this only ranks who is worth activating | fast |
| `activate` | for candidates above `thesis.activation_threshold`: generate `OutreachDraft` (goal: trigger a real application), persist to outbound queue. **Never send email; never auto-invest.** Optionally auto-emit a `ProcessingTicket` with `track="outbound"` for demo purposes (config flag `AUTO_PROCESS_OUTBOUND`) | strong |

**Edges:**

```
START → plan_queries → scan_channels → resolve_candidates
resolve_candidates —route_worth_research→ { "research": deep_research, "skip": quick_score }
deep_research → quick_score → activate → END
```

**Acceptance criteria:**
- Cron fires without overlapping runs (skip if previous scan still running).
- A founder discovered by scan and later applying inbound resolves to the
  SAME canonical Founder (this is the money demo for dedup).
- `deep_research` respects its tool-call budget and degrades gracefully on
  rate limits (partial dossier + low confidence, never a crash).
- Every dossier fact traces to a stored Signal id.

---

## 5. HANDOFF CONTRACT — `ProcessingTicket`

The ONLY interface between intake graphs and the Processing graph. Both
tracks produce it; Processing accepts nothing else.

```
ProcessingTicket:
    opportunity_id: str
    track: "inbound" | "outbound"
    thesis: Thesis                  # frozen copy at intake time
    founder_id: str
    company_id: str
    signal_ids: list[str]           # evidence available at handoff
    claim_ids: list[str]            # inbound: extracted claims; outbound: claims
                                    # derived from the ResearchDossier
    handoff_at: iso timestamp
```

Handoff mechanism: `emit_ticket` / `activate` writes the Opportunity row
(stage="queued") and calls
`processing_graph.ainvoke(ticket_to_state(ticket), config={"configurable": {"thread_id": opportunity_id}})`.
Keep the invoke behind a small `enqueue_processing(ticket)` helper so it can
later be swapped for a real queue without touching graph code.

---

## 6. GRAPH 3 — PROCESSING (3-axis scoring, validation, memo, decision)

**Trigger:** `enqueue_processing(ticket)` from either intake graph.
**Human-in-the-loop:** compiled with `interrupt_before=["decision_gate"]`;
resumed by `POST /decision/{opportunity_id}` via `Command(resume=...)`.

**State — `ProcessingState(TypedDict)`:**

```
opportunity_id: str
track: "inbound" | "outbound"
thesis: Thesis
founder: Founder
company: Company
signals: list[Signal]                 # hydrated from signal_ids
claims: list[Claim]
axis_scores: Annotated[dict[str, AxisScore], merge_axis_dicts]  # reducer: merge KEYS, never average
contradictions: list[Contradiction]
validation_round: int                 # loop guard, max 2
memo: Memo | None
decision: Decision | None
stage_timestamps: dict[str, str]
```

**Nodes:**

| Node | Does | LLM |
|---|---|---|
| `hydrate` | load founder history, signals, claims from DB by ids; stamp `processing_started` | none |
| `founder_axis` ∥ | score WHO the person is. Inputs: founder score history (ONE input, not a substitute), signals, claims. **Cold-start path is mandatory (see §8 prompt):** no track record ⇒ score from public-footprint proxies with LOW confidence, never a silent zero | strong → `AxisScore` |
| `market_axis` ∥ | market sizing sanity, competitor clusters, SWOT; bullish/neutral/bear through the thesis lens | strong → `AxisScore` |
| `idea_vs_market_axis` ∥ | does the idea survive scrutiny as-is; if not, is the team strong enough to pivot? Independent — must NOT read the other axes' outputs | strong → `AxisScore` |
| `validator` | per-claim fact-check: pick external check (GitHub stars → GitHub API, "launched on HN" → HN search, …) via `verify_claim_external`; assign TrustScore; detect claim-vs-claim contradictions; fetched evidence saved as new Signals | strong → `TrustScore`/`Contradiction` |
| `memo_writer` | generate the 5 required sections; every factual sentence cites claim/evidence ids; missing data → `gaps[]` entries; post-validate in code that (a) all citations resolve, (b) required sections present; attach LangSmith `trace_ref` | strong → `Memo` |
| `decision_gate` | interrupt point; on resume, validate/normalize the human `Decision` | none |
| `memory_writeback` | ONLY node persisting conclusions: one transaction writes decision, 3 axis scores, appended Founder Score point, final timestamps | none |

**Edges:**

```
START → hydrate → [founder_axis, market_axis, idea_vs_market_axis]   # parallel fan-out
[3 axes] → validator                                                  # join
validator —route_validation→ { "retry": [3 axes],   # if severe contradictions AND validation_round < 2
                               "ok": memo_writer }
memo_writer → decision_gate → memory_writeback → END
```

On retry, contradictions are present in state so the axis agents re-score
with the disputed claims visible.

**Acceptance criteria:**
- Ticket → memo (awaiting human) in < 5 min on seed data.
- The seeded lying deck produces ≥1 `contradicted` claim and triggers exactly
  one retry loop.
- The cold-start seed founder gets all three axis scores with
  `founder_axis.confidence < 0.5` and an explicit rationale — never null/zero.
- `GET /opportunities/{id}/status` reads latest checkpoint (no extra
  bookkeeping) and exposes `elapsed_seconds` per stage.
- Approve resumes the run and completes writeback in < 5s.

---

## 7. Cross-cutting requirements (all three graphs)

- **Checkpointing:** one `PostgresSaver` (dev fallback SqliteSaver) shared by
  all graphs; state snapshot after every node.
- **Structured output everywhere:** every LLM call uses
  `with_structured_output(<pydantic model>)`. Free-text node outputs are
  banned.
- **Model routing:** `get_fast_llm()` for pre_screen/extraction/planning,
  `get_strong_llm()` for axes/validator/memo/research. Centralized in one
  factory module.
- **Instrumentation:** every node appends to `stage_timestamps`; LangSmith
  tracing on for all graphs; the processing run's trace id is stored on the
  memo (`trace_ref`) to power the UI "show reasoning" panel.
- **Statelessness:** nodes read only from state + repository functions; no
  module-level mutable state (checkpoint/resume safety).
- **Repository boundary:** nodes never write SQL; all DB access through
  `tools.py` repository functions. Signals table is INSERT-only.
- **Seed data:** `load_seed_signals()` provides 15–20 synthetic founders
  including 2–3 with seeded contradictions and 2 cold-start profiles. All
  tests and the demo run on this.
- **Graceful degradation:** external API failure ⇒ mark affected claims
  `unverified` with a note, never crash a run.

---

## 8. Prompts (system-prompt briefs per LLM node)

These are prompt SPECIFICATIONS — implement as system prompts, keep them in
a `prompts.py` with one constant per node. Shared preamble for all:
*"You are a component of a venture-capital analysis system. You must respond
only via the provided structured schema. Never invent facts: every factual
statement must reference provided evidence ids. If evidence is missing, say
so explicitly and lower your confidence."*

**`pre_screen` (fast):**
"Given the thesis and the extracted application content, decide pass/reject
on viability only. Reject only clearly non-viable submissions (spam,
incoherent, categorically outside thesis hard filters already checked in
code). When uncertain, PASS — downstream analysis is the judge. Always
return a one-sentence reason."

**`extract_claims` (fast):**
"Extract every checkable factual assertion from the deck pages provided.
One claim per assertion, category ∈ {traction, revenue, team, market},
verbatim-faithful text, exact source_pointer (page number given in input).
Do not extract opinions or vision statements. Do not assess truth — leave
trust empty."

**`founder_axis` (strong):**
"Score the founder(s) 0–100 on capability to build a venture-scale company,
with trend and confidence. Weigh: track record (founder score history
provided — one input among several), shipping velocity, domain expertise,
evidence quality. COLD-START RULE: if the founder has no track record
(no repos, no funding, no network signals), you must still score using
public-footprint proxies — quality/specificity of the application text,
domain expertise revealed in writing, velocity of whatever exists — and set
confidence low (≤0.5) with a rationale naming the missing evidence. A silent
low score without explanation is a failure. Cite evidence ids per point."

**`market_axis` (strong):**
"Assess the market through the provided fund thesis: sizing sanity check
(flag implausible TAM claims), competitor clusters (named), SWOT bullets,
verdict bullish/neutral/bear mapped to score. A great market outside the
thesis still scores low against this fund's lens — say so explicitly.
Cite evidence ids; state assumptions."

**`idea_vs_market_axis` (strong):**
"Judge fit: does this idea, as-is, survive scrutiny in this market? If not,
is this specific team strong enough to pivot? Do not use or reference the
other axes' scores. Distinguish 'wrong idea, right team' from 'right idea,
wrong team' explicitly in the rationale. Cite evidence ids."

**`validator` (strong):**
"For each claim: determine what external evidence could verify it, use the
verification results provided by tools, and assign status
verified/unverified/contradicted with confidence and supporting/conflicting
evidence ids. Cross-check claims against EACH OTHER for internal
contradictions (e.g. revenue vs founding date). Be adversarial: your job is
to catch what the primary analysis missed. Never mark verified without at
least one independent evidence id."

**`memo_writer` (strong):**
"Write the investment memo with exactly these sections: Company snapshot
(one paragraph), Investment hypotheses (bullets), SWOT, Problem & product,
Traction & KPIs. Every factual sentence must carry a claim/evidence citation
id in brackets. Where required information is missing, add a gaps[] entry
like 'Cap table: not disclosed' — NEVER fabricate, never silently omit. Be
as brief as clarity allows; padding is penalized. End with recommendation
invest/pass/review justified against the thesis and the three axis scores
WITHOUT averaging them — if the axes disagree, surface the disagreement as
the central tension of the memo."

**`plan_queries` (fast, outbound):**
"Translate the fund thesis into concrete search queries per channel:
GitHub topics/search strings, arXiv categories/keywords, HN keywords.
3–5 queries per channel, specific over broad."

**`deep_research` agent (strong, outbound):**
"You research one founder/candidate with the provided tools. Goal: a dossier
covering identity confirmation, what they've shipped, technical depth,
public footprint, and any funding history. Follow promising links (personal
site, docs, launch posts). Respect the tool budget; when it's exhausted,
stop and write the dossier from what you have, listing open questions.
Every fact must carry the source url/signal id. Mark inferences as
inferences."

**`activate` outreach draft (strong, outbound):**
"Draft a short, specific outreach message to this founder. Reference the
concrete work that triggered our interest (cite it), state who we are and
the $100K/24h proposition, and ask them to apply. No flattery padding, no
investment promise — the goal is to trigger an application."

---

## 9. Repo layout expected

```
vc_brain/
  models.py        # contract: domain models + 3 state TypedDicts + reducer
  tools.py         # external clients (GitHub/HN/arXiv/pymupdf/LLM factories)
                   # + repository (all SQL) + verify_claim_external
  prompts.py       # one constant per LLM node (§8)
  nodes_inbound.py
  nodes_outbound.py
  nodes_processing.py
  agents.py        # build_inbound_graph / build_outbound_graph /
                   # build_processing_graph, get_checkpointer,
                   # enqueue_processing, start/resume/status helpers, trigger_scan
  seed.py          # synthetic founders incl. seeded contradictions + cold-start
  api.py           # FastAPI: /apply /scan /opportunities /decision /query /thesis
```

## 10. Build order

1. `models.py` (all three states + ProcessingTicket) — freeze first.
2. `seed.py` + repository functions returning seed data.
3. `build_processing_graph()` with dummy nodes end-to-end (interrupt + resume
   working) — this is the demo spine.
4. Inbound graph end-to-end → ticket → processing.
5. Real processing nodes (validator + founder_axis cold-start are the graded
   differentiators).
6. Outbound graph: scan_channels + quick_score + activate first;
   `deep_research` agent last (highest risk, cap its budget).
