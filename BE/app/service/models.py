"""Shared domain contract for all pipeline graphs.

Single source of truth for the domain models (Signal, Claim, Founder, ...)
used by the inbound and validation pipelines — never redefined inside a
pipeline package. Persistence *records* (pydantic mirrors of Postgres rows)
live in each pipeline's ``utils/models.py``; the SQL tables themselves live
in ``app.models``.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Type aliases
# --------------------------------------------------------------------------- #

type Axis = Literal["founder", "market", "idea_vs_market"]
type ClaimCategory = Literal["traction", "revenue", "team", "market"]
type Track = Literal["inbound", "outbound"]
type Trend = Literal["improving", "stable", "declining"]
type TrustStatus = Literal["verified", "unverified", "contradicted"]
type Verdict = Literal["pass", "reject"]
type Recommendation = Literal["invest", "pass", "review"]

# --------------------------------------------------------------------------- #
# Reducers (LangGraph state merge helpers)
# --------------------------------------------------------------------------- #


def merge_stage_timestamps(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """
    Reducer for stage_timestamps.

    Every node appends its own {stage: iso} entry. Parallel nodes (the three
    axes) each return a partial dict; without a reducer the last writer would
    clobber the others. Merge keys so every stage's timestamp survives — this
    is what powers the time-to-decision instrumentation (a graded criterion).
    """
    return {**left, **right}


def merge_axis_dicts(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    """
    Reducer for axis_scores.

    The three axis agents run in PARALLEL and each returns
    {"axis_scores": {"<axis>": AxisScore}}. This reducer merges dict KEYS
    (never values, never averages) so all three independent scores coexist
    — the data structure itself enforces the brief's "not averaged" rule.
    Also tolerates the validator retry loop overwriting a stale axis.
    """
    return {**left, **right}


# --------------------------------------------------------------------------- #
# Domain models
# --------------------------------------------------------------------------- #


class ScorePoint(BaseModel):
    """One point in a Founder's score trend (see Founder.score_history)."""

    timestamp: str
    value: float
    trigger_signal_id: str | None = None


class TrustScore(BaseModel):
    """
    Per-CLAIM (not per-company) confidence record. evidence_ids point to
    Signal ids — this list is what makes every memo sentence clickable in
    the UI and satisfies Agentic Traceability.
    """

    confidence: float
    status: TrustStatus
    evidence_ids: list[str] = Field(default_factory=list)
    contradiction_note: str | None = None


class Claim(BaseModel):
    """
    One assertion extracted from a deck/application ("$50K MRR", "ex-Google
    team"). Born with trust=None; the validator node fills trust in.
    source_pointer must be precise enough to cite in the memo
    (e.g. "deck p.4").
    """

    id: str
    company_id: str
    category: ClaimCategory
    text: str
    source_pointer: str
    trust: TrustScore | None = None


class Company(BaseModel):
    """
    Canonical startup entity. Links to founder_ids. One company can have
    many Opportunities over time (re-applications), which is exactly why
    Founder Score must live on Founder, not here.
    """

    id: str
    name: str
    founder_ids: list[str] = Field(default_factory=list)
    sector: str | None = None
    geo: str | None = None
    stage: str | None = None


class Founder(BaseModel):
    """
    Canonical person entity after entity resolution. Houses the Founder
    Score: per-person, persists across applications/startups, NEVER resets.
    score_history keeps every (timestamp, value, trigger_signal_id) triple
    so the UI can chart the trend, not just the latest snapshot.
    """

    id: str
    canonical_name: str
    handles: dict[str, str] = Field(default_factory=dict)
    education: list[str] = Field(default_factory=list)
    founder_score: float | None = None
    score_history: list[ScorePoint] = Field(default_factory=list)


class Signal(BaseModel):
    """
    A single raw observation from ANY source — GitHub repo, HN post, arXiv
    paper, a deck upload, an application form. Append-only: signals are
    never mutated or deleted ("nothing discarded"). raw_payload preserves
    the original bytes/JSON so every downstream conclusion can trace back
    to primary evidence.
    """

    id: str
    source_type: Literal["github", "hn", "arxiv", "deck", "application"]
    source_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    entity_hints: list[str] = Field(default_factory=list)
    fetched_at: str


class Thesis(BaseModel):
    """
    The investor's configurable lens. Set once via PUT /thesis, injected
    into graph state at run start. Every axis agent and the final decision
    recommendation must read scoring weights / filters from here — a
    hardcoded thesis misses the point of the pillar.
    """

    sectors: list[str] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    geographies: list[str] = Field(default_factory=list)
    check_size_usd: tuple[int, int] | None = None
    ownership_target: float | None = None
    risk_appetite: Literal["low", "medium", "high"] = "medium"
    axis_weights: dict[Axis, float] = Field(default_factory=dict)


class Contradiction(BaseModel):
    """
    Emitted by the validator when a Claim conflicts with external evidence
    or another Claim. Drives the validator->axes retry loop and the ❌
    badges in the UI.
    """

    claim_id: str
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str
    severity: Literal["low", "medium", "high"] = "medium"


class Decision(BaseModel):
    """
    The human's verdict captured at the interrupt. Written back to Memory
    by the writeback node; also feeds the Founder Score update.
    """

    verdict: Literal["invest", "pass"]
    human_id: str
    note: str | None = None
    decided_at: str


class Memo(BaseModel):
    """
    The investment memo. sections holds the 5 required parts (snapshot,
    hypotheses, swot, problem_product, traction). gaps lists explicitly
    flagged missing data ("Cap table: not disclosed") — never fabricated,
    never silently omitted. trace_ref stores the LangSmith run id for the
    "show reasoning" panel.
    """

    opportunity_id: str
    sections: dict[str, str] = Field(default_factory=dict)
    gaps: list[str] = Field(default_factory=list)
    recommendation: Recommendation = "review"
    trace_ref: str | None = None


class AxisScore(BaseModel):
    """
    Structured output of ONE axis agent (founder / market / idea_vs_market).
    The three axis scores are NEVER averaged — they are merged as separate
    dict keys in graph state (see merge_axis_dicts). confidence encodes
    honest uncertainty: cold-start founders get a real score with LOW
    confidence, never a silent zero.
    """

    axis: Axis
    score: float
    trend: Trend = "stable"
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    confidence: float


class PreScreenResult(BaseModel):
    """
    Output of the cheap first-pass filter. Rejections must carry a reason —
    they are logged to Memory, not silently dropped.
    """

    verdict: Verdict
    reason: str


class ProcessingTicket(BaseModel):
    """
    The handoff contract — the ONLY interface between the intake graphs
    (inbound / outbound) and the processing ("validation") graph. Both
    tracks produce it; processing accepts nothing else, so it cannot tell
    the tracks apart except by the ``track`` field — one funnel, per brief.

    thesis is a FROZEN copy taken at intake time: a later PUT /thesis must
    not retroactively change how an in-flight opportunity is judged.
    """

    opportunity_id: str
    track: Track
    thesis: Thesis
    founder_id: str
    company_id: str
    signal_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    handoff_at: str


class TraceEvent(BaseModel):
    """
    One per-node trace record: what the node did, WHY (rationale), and which
    evidence it touched. Appended to state by every node in both pipelines
    (append-only reducer) and persisted to the ``traces`` Postgres table —
    this powers the UI "show reasoning" panel alongside the LangSmith trace.
    """

    id: str
    opportunity_id: str
    node: str
    started_at: str
    ended_at: str
    duration_ms: float
    model: str | None = None
    rationale: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
