"""Validation (processing) pipeline models — Graph 3 state, LLM schemas, persistence records.

Same three families as the inbound pipeline:

1. ``ProcessingState`` — the TypedDict flowing along every edge of Graph 3.
2. LLM output schemas for ``with_structured_output`` (validator + memo; the
   three axis agents return the shared ``AxisScore`` directly).
3. Persistence records — pydantic mirrors of the future PostgreSQL rows,
   accepted by the repository stubs in ``tools.py`` today.

Domain models come from the shared contract ``app.service.models``.
"""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from pydantic import BaseModel, Field

from app.service.models import (
    AxisScore,
    Claim,
    Company,
    Contradiction,
    Decision,
    Founder,
    Memo,
    Recommendation,
    Signal,
    Thesis,
    TraceEvent,
    Track,
    Trend,
    TrustStatus,
    merge_axis_dicts,
    merge_stage_timestamps,
)

# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #


class ProcessingState(TypedDict, total=False):
    """
    State of Graph 3 (the VC brain). Checkpointed after every node;
    compiled with ``interrupt_before=["decision_gate"]`` — the one human in
    the loop.

    Reducers:
      - axis_scores: merge KEYS, never values — the data structure itself
        enforces the "never average the three axes" hard rule
      - signals / trace: append-only (validator adds fetched evidence)
      - stage_timestamps: key-merge (time-to-decision instrumentation)
    """

    opportunity_id: str
    track: Track
    thesis: Thesis
    founder: Founder | None
    company: Company | None
    signals: Annotated[list[Signal], operator.add]
    claims: list[Claim]
    axis_scores: Annotated[dict[str, AxisScore], merge_axis_dicts]
    contradictions: list[Contradiction]
    validation_round: int  # loop guard, max 2
    memo: Memo | None
    decision: Decision | None
    stage_timestamps: Annotated[dict[str, str], merge_stage_timestamps]
    trace: Annotated[list[TraceEvent], operator.add]


# --------------------------------------------------------------------------- #
# LLM output schemas
# --------------------------------------------------------------------------- #


class ClaimVerdict(BaseModel):
    """The validator's per-claim trust assignment (Trust Score is per CLAIM)."""

    claim_id: str
    status: TrustStatus
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    note: str = Field(
        default="",
        description="Short justification; mandatory when status != unverified",
    )


class ValidatorOutput(BaseModel):
    """Full output of the validator LLM call."""

    verdicts: list[ClaimVerdict] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    rationale: str = Field(
        description="One paragraph: what was checked, what could not be, and why"
    )


class MemoDraft(BaseModel):
    """The memo writer's structured output — the 5 required sections, nothing else."""

    sections: dict[str, str] = Field(
        description=(
            "Exactly these keys: snapshot, hypotheses, swot, problem_product, "
            "traction. Every factual sentence carries a claim/evidence id in "
            "brackets, e.g. [claim-ab12cd34ef56]."
        )
    )
    gaps: list[str] = Field(
        default_factory=list,
        description='Explicitly flagged missing data, e.g. "Cap table: not disclosed"',
    )
    recommendation: Recommendation = "review"


# --------------------------------------------------------------------------- #
# Persistence records — the exact PostgreSQL attributes (tables set up in a
# later run). One class == one table row. Repository stubs accept these.
# --------------------------------------------------------------------------- #


class AxisScoreRecord(BaseModel):
    """Row of ``axis_scores`` — one per (opportunity, axis, validation_round)."""

    opportunity_id: str  # fk
    axis: str  # founder | market | idea_vs_market
    score: float  # 0..100
    trend: Trend
    confidence: float  # 0..1, honest uncertainty (cold-start => low)
    rationale: str
    evidence_ids: list[str] = Field(default_factory=list)
    validation_round: int
    scored_at: str


class ContradictionRecord(BaseModel):
    """Row of ``contradictions`` — drives the retry loop and the UI badges."""

    opportunity_id: str  # fk
    claim_id: str
    conflicting_evidence_ids: list[str] = Field(default_factory=list)
    explanation: str
    severity: str  # low | medium | high
    detected_at: str


class MemoRecord(BaseModel):
    """Row of ``memos`` — sections/gaps as jsonb; trace_ref = LangSmith run id."""

    opportunity_id: str  # pk/fk
    sections: dict[str, str] = Field(default_factory=dict)  # jsonb
    gaps: list[str] = Field(default_factory=list)
    recommendation: Recommendation
    trace_ref: str | None = None
    created_at: str


class DecisionRecord(BaseModel):
    """Row of ``decisions`` — the human verdict captured at the interrupt."""

    opportunity_id: str  # pk/fk
    verdict: str  # invest | pass
    human_id: str
    note: str | None = None
    decided_at: str


class FounderScorePointRecord(BaseModel):
    """Row of ``founder_score_points`` — append-only; the score NEVER resets."""

    founder_id: str  # fk
    timestamp: str
    value: float  # 0..100
    trigger_signal_id: str | None = None


class TraceRecord(BaseModel):
    """Row of ``traces`` — mirrors TraceEvent (same table as inbound writes)."""

    id: str  # pk
    opportunity_id: str  # fk
    node: str
    started_at: str
    ended_at: str
    duration_ms: float
    model: str | None = None
    rationale: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list)
