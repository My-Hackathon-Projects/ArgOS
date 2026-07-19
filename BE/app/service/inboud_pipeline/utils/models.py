"""Inbound pipeline models — graph state, LLM output schemas, persistence records.

Three families:

1. ``InboundState`` — the TypedDict flowing along every edge of Graph 1.
2. LLM output schemas — what ``with_structured_output`` returns. They carry NO
   ids (the LLM must never invent identifiers); nodes assign ids afterwards.
3. Persistence records — pydantic mirrors of the future PostgreSQL rows. The
   repository stubs in ``tools.py`` accept these today; the real SQL layer
   drops in behind them in a later run without touching nodes.

Domain models (Signal, Claim, Founder, ...) come from the shared contract
``app.service.models`` — never redefined here.
"""

from __future__ import annotations

import operator
from typing import Annotated, Any, Literal, TypedDict

from pydantic import BaseModel, Field

from app.service.models import (
    Claim,
    ClaimCategory,
    Company,
    Founder,
    PreScreenResult,
    ProcessingTicket,
    Signal,
    Thesis,
    TraceEvent,
    Track,
    merge_stage_timestamps,
)

# --------------------------------------------------------------------------- #
# Graph state
# --------------------------------------------------------------------------- #


class InboundState(TypedDict, total=False):
    """
    State of Graph 1 (inbound intake). Checkpointed after every node.

    Reducers:
      - signals: append-only (operator.add) — observations are never replaced
      - trace: append-only — each node adds its own TraceEvent
      - stage_timestamps: key-merge — powers time-to-decision instrumentation
    """

    opportunity_id: str
    thesis: Thesis
    raw_deck: bytes | None
    company_name: str
    signals: Annotated[list[Signal], operator.add]
    founder: Founder | None
    company: Company | None
    claims: list[Claim]  # trust=None at this stage; validator fills it later
    prescreen: PreScreenResult | None
    ticket: ProcessingTicket | None
    stage_timestamps: Annotated[dict[str, str], merge_stage_timestamps]
    trace: Annotated[list[TraceEvent], operator.add]


# --------------------------------------------------------------------------- #
# LLM output schemas (structured output only — ids assigned by nodes)
# --------------------------------------------------------------------------- #


class ExtractedClaim(BaseModel):
    """One checkable factual assertion extracted from a deck page."""

    category: ClaimCategory
    text: str = Field(description="Verbatim-faithful assertion text")
    source_pointer: str = Field(description='Exact page pointer, e.g. "deck p.4"')


class ClaimExtraction(BaseModel):
    """Output of the extract_claims fast-LLM call."""

    claims: list[ExtractedClaim] = Field(default_factory=list)
    rationale: str = Field(
        description="One short paragraph: what was extracted, what was skipped and why"
    )


# --------------------------------------------------------------------------- #
# Persistence records — the exact PostgreSQL attributes (tables set up in a
# later run). One class == one table row. Repository stubs accept these.
# --------------------------------------------------------------------------- #

OpportunityStage = Literal["received", "screened", "rejected", "queued"]


class OpportunityRecord(BaseModel):
    """Row of ``opportunities`` — one funnel entry per application/scan hit."""

    opportunity_id: str  # pk; doubles as LangGraph thread_id
    track: Track
    company_id: str | None = None
    founder_id: str | None = None
    stage: OpportunityStage
    thesis_json: dict[str, Any] = Field(default_factory=dict)  # jsonb, frozen at intake
    deck_blob_key: str | None = None  # MinIO/S3 key of the raw deck PDF
    created_at: str
    updated_at: str


class SignalRecord(BaseModel):
    """Row of ``signals`` — INSERT-only, never UPDATE/DELETE (nothing discarded)."""

    id: str  # pk, deterministic (content hash) so re-uploads are idempotent
    source_type: str
    source_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)  # jsonb, primary evidence
    entity_hints: list[str] = Field(default_factory=list)
    fetched_at: str
    opportunity_id: str | None = None  # fk, nullable (outbound scan signals)


class FounderRecord(BaseModel):
    """Row of ``founders`` — canonical person; Founder Score NEVER resets."""

    id: str  # pk
    canonical_name: str
    handles: dict[str, str] = Field(default_factory=dict)  # jsonb
    education: list[str] = Field(default_factory=list)
    founder_score: float | None = None  # current snapshot 0..100
    score_history: list[dict[str, Any]] = Field(default_factory=list)  # jsonb ScorePoints


class CompanyRecord(BaseModel):
    """Row of ``companies`` — canonical startup entity."""

    id: str  # pk
    name: str
    founder_ids: list[str] = Field(default_factory=list)
    sector: str | None = None
    geo: str | None = None
    stage: str | None = None


class ClaimRecord(BaseModel):
    """Row of ``claims`` — trust_* columns filled by the validation pipeline."""

    id: str  # pk
    opportunity_id: str
    company_id: str
    category: ClaimCategory
    text: str
    source_pointer: str
    trust_status: str | None = None  # verified|unverified|contradicted
    trust_confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list)


class RejectionRecord(BaseModel):
    """Row of ``rejections`` — rejected != deleted; reason stays queryable."""

    opportunity_id: str
    reason: str
    rejected_at: str


class TraceRecord(BaseModel):
    """Row of ``traces`` — mirrors TraceEvent; the persisted reasoning trail."""

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
