"""API response contracts. Pydantic models the endpoints declare via `response_model=`.

Separate from `models.py` (SQLAlchemy ORM) on purpose: these are the wire shapes the
frontend generates its TS types from (openapi.json -> orval). Keep them 1:1 with what
`main.py` returns. Changing a field here changes the FE client -> regenerate.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, model_validator


class HealthResponse(BaseModel):
    status: str
    signals: int


class SignalListItem(BaseModel):
    id: str
    source: str
    signal_type: str
    title: str | None
    summary: str | None
    url: str | None
    source_reliability: float | None
    occurred_at: datetime | None
    ingested_at: datetime


class IngestResponse(BaseModel):
    id: str
    created: bool


class FounderListItem(BaseModel):
    id: str
    display_name: str | None
    status: str
    discovery_confidence: float | None
    founder_score: float | None
    current_company: str | None
    occupation: str | None
    city: str | None
    signal_count: int


class FounderIdentity(BaseModel):
    github: str | None
    twitter: str | None
    linkedin: str | None
    website: str | None


class FounderSignal(BaseModel):
    source: str
    signal_type: str
    title: str | None
    summary: str | None
    url: str | None
    occurred_at: datetime | None
    source_reliability: float | None
    resolution_confidence: float | None
    resolution_method: str | None


class FounderClaimItem(BaseModel):
    statement: str
    category: str | None
    trust_score: float | None
    status: str
    evidence_count: int
    updated_at: datetime | None


class FounderDetail(BaseModel):
    id: str
    display_name: str | None
    status: str
    discovery_confidence: float | None
    founder_score: float | None
    current_company: str | None
    occupation: str | None
    city: str | None
    education: list[dict] | None
    first_discovered_at: datetime | None
    last_checked_at: datetime | None
    identity: FounderIdentity
    signals: list[FounderSignal]
    claims: list[FounderClaimItem]


class ChannelItem(BaseModel):
    name: str
    type: str | None
    domain: str | None
    enabled: bool
    yield_count: int


class ThesisResponse(BaseModel):
    name: str | None
    industries: list[str] | None
    geo: list[str] | None
    stage: list[str] | None
    keywords: list[str] | None
    founder_preferences: dict | None


class DiscoveryRunResponse(BaseModel):
    new_founders: int
    resolved_to_existing: int
    new_signals: int
    job_run_id: str
    stats: dict
    trace: list


# ── Market research ──────────────────────────────────────────────────────────
class MarketFigureItem(BaseModel):
    metric: str | None
    value: str | None
    basis: str | None  # reported | estimated_bottom_up | gap
    confidence: float | None
    trust_score: float | None
    status: str | None
    url: str | None  # provenance — the source this figure was extracted from


class MarketCompetitorItem(BaseModel):
    name: str
    cluster: str | None
    positioning: str | None
    is_emerging_threat: bool
    trust_score: float | None
    url: str | None


class MarketComparableItem(BaseModel):
    name: str
    stage: str | None
    round_size: str | None
    valuation: str | None
    date: str | None
    similarity_rationale: str | None
    trust_score: float | None
    url: str | None


class MarketAxisView(BaseModel):
    verdict: str
    score: float | None
    trend: str
    rationale: str | None
    confidence: float | None
    gaps: list[str]


class MarketOpportunityListItem(BaseModel):
    id: str
    company_name: str | None
    sector: str | None
    geo: str | None
    verdict: str | None
    score: float | None
    trend: str | None


class MarketAnalysisResponse(BaseModel):
    id: str
    company_name: str | None
    idea: str | None
    sector: str | None
    geo: str | None
    axis: MarketAxisView | None
    sizing: list[MarketFigureItem]
    kpi: list[MarketFigureItem]
    competitors: list[MarketCompetitorItem]
    comparables: list[MarketComparableItem]


# ── Inbound intake ───────────────────────────────────────────────────────────
class ApplyResponse(BaseModel):
    opportunity_id: str
    status: str  # screening | rejected
    prescreen_verdict: str  # pass | reject
    prescreen_reason: str
    signals_ingested: int
    claims_minted: int
    idea: str | None
    sector: str | None
    geo: str | None


# ── Opportunities (manual-dispatch entry for screening/memo) ─────────────────
class OpportunityCreate(BaseModel):
    founder_id: uuid.UUID | None = None
    company_name: str | None = None
    idea: str | None = None
    sector: str | None = None
    geo: str | None = None

    @model_validator(mode="after")
    def require_screening_subject(self) -> "OpportunityCreate":
        # An opportunity without an idea or a sector has nothing to screen against.
        if not ((self.idea or "").strip() or (self.sector or "").strip()):
            raise ValueError("opportunity needs an idea or a sector")
        return self


class OpportunityAxisSummary(BaseModel):
    axis: str  # founder|market|idea — independent rows, NEVER averaged
    score: float | None
    verdict: str
    trend: str
    confidence: float | None
    rationale: str | None = None
    evidence: dict | None = None  # {claim_ids, urls} — provenance for the FE
    gaps: list[str] = []


class OpportunityListItem(BaseModel):
    id: str
    founder_id: str | None
    company_name: str | None
    idea: str | None
    sector: str | None
    geo: str | None
    status: str
    created_at: datetime
    axes: list["OpportunityAxisSummary"]


class OpportunityDetail(OpportunityListItem):
    decision: str | None


class MemoView(BaseModel):
    opportunity_id: str
    sections: dict | None  # {snapshot, hypotheses:[{statement, evidence_claim_ids}], swot, axes}
    recommendation: str | None
    confidence: float | None
    gaps: list[str]
    quality: dict | None  # deterministic anchor scorecard (citations resolved, sections present)
    generated_at: datetime
