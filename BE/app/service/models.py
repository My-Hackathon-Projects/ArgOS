"""models.py — the data contract.

The "constitution" of the project. Every object exchanged between nodes,
written to Memory, or serialized by the API derives from a model here. Nobody
changes this file unilaterally — schema changes are announced at standup.

Layering rule: domain models live here and in Postgres. ``GraphState`` is the
single object flowing along every LangGraph edge. View models
(``OpportunityCard``, ``MemoView``, …) belong to the API layer, **not** here —
the frontend must never see ``GraphState`` or raw domain rows.

These pydantic models double as LLM structured-output schemas: nodes call
``llm.with_structured_output(<Model>)`` and get one of these back.
"""

from __future__ import annotations

from typing import Annotated, Literal, TypedDict

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Enums / literals — single source of truth for the pipeline's vocabulary.
# --------------------------------------------------------------------------- #
Axis = Literal["founder", "market", "idea_vs_market"]
Track = Literal["inbound", "outbound"]
TrustStatus = Literal["verified", "unverified", "contradicted"]
ClaimCategory = Literal["traction", "revenue", "team", "market"]
Verdict = Literal["invest", "pass"]
Recommendation = Literal["invest", "pass", "review"]
Trend = Literal["improving", "stable", "declining"]


class Thesis(BaseModel):
    """
    The investor's configurable lens (FR-1). Set once via PUT /thesis,
    injected into GraphState at run start. Every axis agent and the final
    decision recommendation must read scoring weights / filters from here —
    a hardcoded thesis misses the point of the pillar (brief FAQ #15).

    Fields to define: sectors, stage, geographies, check_size,
    ownership_target, risk_appetite, and optional per-axis weights.
    """

    sectors: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    check_size_usd: tuple[int, int] | None = None
    ownership_target: float | None = None  # 0..1
    risk_appetite: Literal["low", "medium", "high"] = "medium"
    # Optional per-axis scoring weights; default equal weighting.
    axis_weights: dict[Axis, float] = Field(
        default_factory=lambda: {
            "founder": 1.0,
            "market": 1.0,
            "idea_vs_market": 1.0,
        }
    )


class ScorePoint(BaseModel):
    """One point in a Founder's score trend (see Founder.score_history)."""

    timestamp: str
    value: float
    trigger_signal_id: str | None = None


class Founder(BaseModel):
    """
    Canonical person entity after entity resolution. Houses the Founder
    Score: per-person, persists across applications/startups, NEVER resets
    (brief FAQ #6). score_history keeps every (timestamp, value,
    trigger_signal_id) triple so the UI can chart the trend, not just the
    latest snapshot.

    Fields to define: id, canonical_name, handles (github/x/linkedin),
    education, founder_score (current), score_history.
    """

    id: str
    canonical_name: str
    handles: dict[str, str] = Field(default_factory=dict)  # {"github": "...", ...}
    education: list[str] = Field(default_factory=list)
    founder_score: float | None = None  # current snapshot, 0..100
    score_history: list[ScorePoint] = Field(default_factory=list)


class Company(BaseModel):
    """
    Canonical startup entity. Links to founder_ids. One company can have
    many Opportunities over time (re-applications), which is exactly why
    Founder Score must live on Founder, not here.

    Fields to define: id, name, founder_ids, sector, geo, stage.
    """

    id: str
    name: str
    founder_ids: list[str] = Field(default_factory=list)
    sector: str | None = None
    geo: str | None = None
    stage: str | None = None


class Signal(BaseModel):
    """
    A single raw observation from ANY source — GitHub repo, HN post, arXiv
    paper, a deck upload, an application form. Append-only: signals are
    never mutated or deleted ("nothing discarded"). raw_payload preserves
    the original bytes/JSON so every downstream conclusion can trace back
    to primary evidence (traceability stretch goal).

    Fields to define: id, source_type, source_url, raw_payload (dict),
    entity_hints (names/handles for resolution), fetched_at.
    """

    id: str
    source_type: Literal["github", "hn", "arxiv", "deck", "application"]
    source_url: str | None = None
    raw_payload: dict = Field(default_factory=dict)
    entity_hints: list[str] = Field(default_factory=list)
    fetched_at: str  # ISO timestamp


class TrustScore(BaseModel):
    """
    Per-CLAIM (not per-company) confidence record (brief FAQ #7).
    evidence_ids point to Signal ids — this list is what makes every memo
    sentence clickable in the UI and satisfies Agentic Traceability.

    Fields to define: confidence (0..1),
    status: verified | unverified | contradicted,
    evidence_ids, contradiction_note.
    """

    confidence: float = Field(ge=0.0, le=1.0)
    status: TrustStatus
    evidence_ids: list[str] = Field(default_factory=list)
    contradiction_note: str | None = None


class Claim(BaseModel):
    """
    One assertion extracted from a deck/application ("$50K MRR", "ex-Google
    team"). Born with trust=None; the validator node fills trust in.
    source_pointer must be precise enough to cite in the memo
    (e.g. "deck p.4").

    Fields to define: id, company_id, category
    (traction|revenue|team|market), text, source_pointer, trust.
    """

    id: str
    company_id: str
    category: ClaimCategory
    text: str
    source_pointer: str  # e.g. "deck p.4"
    trust: TrustScore | None = None


class Contradiction(BaseModel):
    """
    Emitted by the validator when a Claim conflicts with external evidence
    or another Claim. Drives the validator->axes retry loop and the ❌
    badges in the UI.

    Fields to define: claim_id, conflicting_evidence_ids, explanation,
    severity.
    """

    claim_id: str
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str
    severity: Literal["low", "medium", "high"] = "medium"


class AxisScore(BaseModel):
    """
    Structured output of ONE axis agent (founder / market /
    idea_vs_market). The three axis scores are NEVER averaged — they are
    merged as separate dict keys in GraphState (see merge_axis_dicts).
    confidence encodes honest uncertainty: cold-start founders get a real
    score with LOW confidence, never a silent zero (FR-9).

    Fields to define: axis, score (0..100),
    trend: improving | stable | declining,
    rationale, evidence_ids, confidence (0..1).
    """

    axis: Axis
    score: float = Field(ge=0.0, le=100.0)
    trend: Trend = "stable"
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class PreScreenResult(BaseModel):
    """
    Output of the cheap first-pass filter. Rejections must carry a reason —
    they are logged to Memory, not silently dropped.

    Fields to define: verdict (pass | reject), reason.
    """

    verdict: Literal["pass", "reject"]
    reason: str


class Memo(BaseModel):
    """
    The investment memo. sections holds the 5 required parts (snapshot,
    hypotheses, swot, problem_product, traction). gaps lists explicitly
    flagged missing data ("Cap table: not disclosed") — never fabricated,
    never silently omitted (brief FAQ #9). trace_ref stores the LangSmith
    run id for the "show reasoning" panel.

    Fields to define: opportunity_id, sections (dict[str, str]), gaps,
    recommendation (invest | pass | review), trace_ref.
    """

    opportunity_id: str
    sections: dict[str, str] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    recommendation: Recommendation = "review"
    trace_ref: str | None = None


class Decision(BaseModel):
    """
    The human's verdict captured at the interrupt. Written back to Memory
    by the writeback node; also feeds the Founder Score update.

    Fields to define: verdict (invest | pass), human_id, note, decided_at.
    """

    verdict: Verdict
    human_id: str
    note: str | None = None
    decided_at: str  # ISO timestamp


class ProcessingTicket(BaseModel):
    """
    The handoff contract (§5) — the ONLY interface between the intake graphs
    (inbound / outbound) and the processing ("validation") graph. Both tracks
    produce it; processing accepts nothing else, so it cannot tell the tracks
    apart except by the ``track`` field — one funnel, per brief.

    thesis is a FROZEN copy taken at intake time: a later PUT /thesis must not
    retroactively change how an in-flight opportunity is judged.
    """

    opportunity_id: str
    track: Track
    thesis: Thesis
    founder_id: str
    company_id: str
    signal_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    handoff_at: str  # ISO timestamp


class TraceEvent(BaseModel):
    """
    One per-node trace record: what the node did, WHY (rationale), and which
    evidence it touched. Appended to state by every node in both pipelines
    (append-only reducer) and persisted later to the ``traces`` Postgres table
    — this powers the UI "show reasoning" panel alongside the LangSmith trace.
    """

    id: str
    opportunity_id: str
    node: str
    started_at: str  # ISO timestamp
    ended_at: str  # ISO timestamp
    duration_ms: float
    model: str | None = None  # LLM used, None for deterministic nodes
    rationale: str  # why the node decided what it decided
    summary: str  # what the node produced
    evidence_ids: list[str] = Field(default_factory=list)


def merge_axis_dicts(left: dict, right: dict) -> dict:
    """
    Reducer for GraphState.axis_scores.

    The three axis agents run in PARALLEL and each returns
    {"axis_scores": {"<axis>": AxisScore}}. This reducer merges dict KEYS
    (never values, never averages) so all three independent scores coexist
    — the data structure itself enforces the brief's "not averaged" rule.
    Should also tolerate the validator retry loop overwriting a stale axis.
    """
    merged = dict(left or {})
    # Right (newer) wins per key — lets a validator retry overwrite a stale
    # axis, while untouched axes are preserved. Never averages values.
    merged.update(right or {})
    return merged


def merge_stage_timestamps(left: dict, right: dict) -> dict:
    """
    Reducer for GraphState.stage_timestamps.

    Every node appends its own {stage: iso} entry. Parallel nodes (the three
    axes) each return a partial dict; without a reducer the last writer would
    clobber the others. Merge keys so every stage's timestamp survives — this
    is what powers the time-to-decision instrumentation (a graded criterion).
    """
    merged = dict(left or {})
    merged.update(right or {})
    return merged


class GraphState(TypedDict, total=False):
    """
    Shared state for the main pipeline graph. Checkpointed to Postgres
    after EVERY node (PostgresSaver), which gives us for free:
      - crash/resume (NFR-9),
      - live RunStatus endpoint (API just reads the latest checkpoint),
      - time-to-decision instrumentation via stage_timestamps diffs,
      - a replayable trace for the reasoning panel.

    Keys:
      opportunity_id: str            — doubles as LangGraph thread_id
      track: "inbound" | "outbound"
      thesis: Thesis
      founder: Founder | None
      company: Company | None
      signals: list[Signal]
      claims: list[Claim]
      prescreen: PreScreenResult | None
      axis_scores: Annotated[dict[str, AxisScore], merge_axis_dicts]
      contradictions: list[Contradiction]
      validation_round: int          — loop guard, max 2
      memo: Memo | None
      decision: Decision | None
      stage_timestamps: dict[str, str]
    """

    opportunity_id: str
    track: Track
    thesis: Thesis
    founder: Founder | None
    company: Company | None
    signals: list[Signal]
    claims: list[Claim]
    prescreen: PreScreenResult | None
    axis_scores: Annotated[dict[str, AxisScore], merge_axis_dicts]
    contradictions: list[Contradiction]
    validation_round: int
    memo: Memo | None
    decision: Decision | None
    stage_timestamps: Annotated[dict[str, str], merge_stage_timestamps]
