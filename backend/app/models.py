"""Minimal scraping-core schema. The shared contract every connector writes into.

Sourcing core + the claims layer:
founder + identity (entity resolution), signal (ingested events), job_run (cron ops),
claim + claim_evidence (corroborated assertions → the rescore seam),
investment_thesis + sourcing_channel (thesis lens + monitored channels).
Opportunity / memo / weight_profile tables come with later features.

See docs/claims-layer.md for how claims relate to signals + scoring.
"""

import uuid
from datetime import date, datetime

from sqlalchemy import (
    ARRAY,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Founder(Base):
    """The person. One row per real human; the Founder Score persists here across startups."""

    __tablename__ = "founder"
    __table_args__ = (
        CheckConstraint(
            "status IN ('candidate', 'needs_review', 'confirmed')", name="ck_founder_status"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str | None]
    founder_score: Mapped[float | None]
    components: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Person attributes (populated by sourcing / resolution).
    first_name: Mapped[str | None]
    last_name: Mapped[str | None]
    dob: Mapped[date | None] = mapped_column(Date)
    city: Mapped[str | None]
    occupation: Mapped[str | None]
    current_company: Mapped[str | None]  # None = pre-company founder (primary target)
    education: Mapped[list | None] = mapped_column(JSONB)  # [{school, degree, field, year}]

    # Outbound lifecycle + uncertainty (Q8).
    status: Mapped[str] = mapped_column(server_default=text("'candidate'"))
    discovery_confidence: Mapped[float | None]  # "is this a real, distinct lead"
    first_discovered_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )  # refresh cursor
    last_claimed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True)
    )  # claim-generation cursor (warm-update gate)

    identities: Mapped[list["Identity"]] = relationship(back_populates="founder")
    signals: Mapped[list["Signal"]] = relationship(back_populates="founder")
    claims: Mapped[list["Claim"]] = relationship(back_populates="founder")


class Identity(Base):
    """One founder → many source handles. Columns act as unique resolution keys."""

    __tablename__ = "identity"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founder.id", ondelete="CASCADE"))
    github: Mapped[str | None]
    twitter: Mapped[str | None]
    linkedin: Mapped[str | None]
    email: Mapped[str | None]
    orcid: Mapped[str | None]
    website: Mapped[str | None]  # strong key for cold-start founders lacking GitHub
    other_socials: Mapped[dict | None] = mapped_column(JSONB)

    founder: Mapped[Founder] = relationship(back_populates="identities")


class Signal(Base):
    """One polymorphic table for every source. (source, external_id) unique → idempotent poll."""

    __tablename__ = "signal"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_signal_source_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str]  # github|arxiv|devpost|producthunt|hn|web|synthetic|inbound
    signal_type: Mapped[str]  # commit|repo|paper|launch|hackathon|profile|post|deck
    external_id: Mapped[str]  # source-native id (web signals use canonical_url)
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder.id", ondelete="SET NULL")
    )
    entity_hint: Mapped[str | None]  # raw handle/name pre-resolution ("github:torvalds")
    url: Mapped[str | None]
    canonical_url: Mapped[str | None]  # normalized artifact URL — global dedup key
    content_hash: Mapped[str | None]  # sha256 of normalized text — catches mirrors/syndication
    title: Mapped[str | None]
    summary: Mapped[str | None]  # short normalized text → feed
    occurred_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    source_reliability: Mapped[float | None]  # per-source prior 0..1
    resolution_confidence: Mapped[float | None]  # "is this signal really this founder's"
    resolution_method: Mapped[str | None]  # exact_key|fuzzy|llm
    sources_seen: Mapped[list | None] = mapped_column(JSONB)  # channels that surfaced this artifact
    raw: Mapped[dict | None] = mapped_column(JSONB)  # full original payload, nothing discarded

    founder: Mapped[Founder | None] = relationship(back_populates="signals")
    claim_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="signal")


class JobRun(Base):
    """One row per connector poll / discovery run → the ops/monitoring panel."""

    __tablename__ = "job_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    new_signals: Mapped[int | None]
    errors: Mapped[str | None]


class InvestmentThesis(Base):
    """The fund lens. Drives discovery (what to look for) and scoring (later)."""

    __tablename__ = "investment_thesis"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None]
    industries: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    geo: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    stage: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(String))
    founder_preferences: Mapped[dict | None] = mapped_column(
        JSONB
    )  # {schools, traits, backgrounds}
    check_size: Mapped[float | None]
    ownership: Mapped[float | None]
    risk: Mapped[str | None]
    free_text: Mapped[str | None]
    is_default: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourcingChannel(Base):
    """A monitored discovery channel — client-facing "what we're watching" + seed for discovery."""

    __tablename__ = "sourcing_channel"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str]
    type: Mapped[str | None]  # launch|hackathon|code|paper|accelerator|web
    domain: Mapped[str | None]  # None = open web
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    thesis_relevant: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    yield_count: Mapped[int] = mapped_column(
        Integer, server_default=text("0")
    )  # channel-quality stretch
    quality_score: Mapped[float | None]
    last_success_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class Claim(Base):
    """A corroborated assertion about a founder — the seam that gates rescoring.

    One claim <- many signals (via claim_evidence). trust_score is a deterministic
    formula over that evidence, not an LLM output. Minting a claim (or a materially
    changed trust_score) bumps updated_at -> triggers a Founder Score recompute;
    a signal that only re-confirms an already-strong claim moves nothing.
    """

    __tablename__ = "claim"
    __table_args__ = (
        CheckConstraint(
            "status IN ('unverified', 'verified', 'contradicted', 'needs_review')",
            name="ck_claim_status",
        ),
        # A claim is anchored to a founder (person-level) OR an opportunity (company/market-level).
        # Market-research claims set opportunity_id + founder_id NULL so they never roll into the
        # Founder Score (which sums claims WHERE founder_id = x). See docs/market-layer.md.
        CheckConstraint(
            "founder_id IS NOT NULL OR opportunity_id IS NOT NULL", name="ck_claim_owner"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Nullable since 0005: founder claims set founder_id; company/market claims (market agent)
    # set opportunity_id instead. The ck_claim_owner CHECK requires >= 1.
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder.id", ondelete="CASCADE")
    )
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity.id", ondelete="CASCADE")
    )
    category: Mapped[
        str
    ]  # publication|technical_skill|achievement|traction|revenue|team|market|market_size|...
    statement: Mapped[str]  # canonical NL claim, shown in memo/UI
    attributes: Mapped[dict | None] = mapped_column(
        JSONB
    )  # structured {venue, year, metric, value}
    trust_score: Mapped[float | None]  # deterministic formula over evidence (== confidence level)
    trust_components: Mapped[dict | None] = mapped_column(
        JSONB
    )  # formula inputs, auditable receipts
    status: Mapped[str] = mapped_column(server_default=text("'unverified'"))
    dedup_key: Mapped[str | None]  # optional deterministic key -> cheap exact attach, skips the LLM
    first_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # bumps on evidence/trust change -> the rescore trigger

    founder: Mapped[Founder | None] = relationship(back_populates="claims")
    opportunity: Mapped["Opportunity | None"] = relationship(back_populates="claims")
    evidence: Mapped[list["ClaimEvidence"]] = relationship(
        back_populates="claim", cascade="all, delete-orphan"
    )


class ClaimEvidence(Base):
    """claim <-> signal (many-to-many). A signal can back many claims; a claim, many signals.

    stance = supports|refutes (a 'refutes' row is a contradiction). This table is both the
    corroboration source (feeds the trust formula) and the provenance link
    (claim -> signal -> url/raw) for agentic traceability.
    """

    __tablename__ = "claim_evidence"
    __table_args__ = (
        UniqueConstraint("claim_id", "signal_id", name="uq_claim_evidence_edge"),
        CheckConstraint("stance IN ('supports', 'refutes')", name="ck_evidence_stance"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    claim_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("claim.id", ondelete="CASCADE"))
    signal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("signal.id", ondelete="CASCADE"))
    stance: Mapped[str]  # supports|refutes
    weight: Mapped[float | None]  # source_reliability x recency x relevance -> feeds trust formula
    extraction_conf: Mapped[float | None]  # LLM confidence that this signal asserts the claim
    rationale: Mapped[str | None]  # short "why", for the traceability panel
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    claim: Mapped[Claim] = relationship(back_populates="evidence")
    signal: Mapped[Signal] = relationship(back_populates="claim_links")


# ── DILIGENCE (0005) — company / opportunity / 3-axis ────────────────────────
# Entity model (see docs/market-layer.md, SYSTEM_DESIGN §4):
#   founder (person, persistent) — optional company (the venture) — opportunity (the deal).
# A founder can exist with no company (pre-idea, cold-start). An opportunity can exist with no
# company (investing in people + idea). Market research runs on an opportunity that has an
# idea/sector; its claims + 3-axis 'market' row hang on the opportunity.


class Company(Base):
    """The venture — optional; created only when a real startup exists."""

    __tablename__ = "company"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str | None]
    website: Mapped[str | None]
    sector: Mapped[str | None]
    geo: Mapped[str | None]
    description: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )


class FounderCompany(Base):
    """founder <-> company (co-founders, serial founders). Independent of any single deal."""

    __tablename__ = "founder_company"
    __table_args__ = (UniqueConstraint("founder_id", "company_id", name="uq_founder_company"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founder.id", ondelete="CASCADE"))
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("company.id", ondelete="CASCADE"))
    role: Mapped[str | None]  # founder|cofounder|cto|...


class Opportunity(Base):
    """The investment opportunity — the diligence/decision unit.

    founder_id and company_id are BOTH nullable: an idea-stage deal is a founder + idea with no
    company row; an inbound deck may arrive before founder resolution. `idea`/`sector`/`geo` are
    denormalized so a company-less opportunity is self-contained enough to research a market for.
    """

    __tablename__ = "opportunity"
    __table_args__ = (
        CheckConstraint(
            "status IN ('screening', 'diligence', 'decided', 'rejected')",
            name="ck_opportunity_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder.id", ondelete="SET NULL")
    )
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("company.id", ondelete="SET NULL")
    )
    company_name: Mapped[str | None]  # denormalized label; works for idea-only opportunities
    idea: Mapped[str | None]  # description / topic being evaluated — the market-research subject
    sector: Mapped[str | None]
    geo: Mapped[str | None]
    source: Mapped[str | None]  # inbound|outbound
    status: Mapped[str] = mapped_column(server_default=text("'screening'"))
    decision: Mapped[str | None]
    first_signal_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    claims: Mapped[list["Claim"]] = relationship(back_populates="opportunity")
    axes: Mapped[list["ThreeAxis"]] = relationship(back_populates="opportunity")


class ThreeAxis(Base):
    """One row per axis per opportunity — Founder/Market/Idea, scored INDEPENDENTLY, never averaged.

    The disagreement between axes is the signal. `evidence` holds the cited claim_ids/urls the
    verdict rests on (provenance); one row per (opportunity, axis) so a re-run upserts.
    """

    __tablename__ = "three_axis"
    __table_args__ = (
        UniqueConstraint("opportunity_id", "axis", name="uq_three_axis_opportunity_axis"),
        CheckConstraint("axis IN ('founder', 'market', 'idea')", name="ck_three_axis_axis"),
        CheckConstraint("verdict IN ('bull', 'neutral', 'bear')", name="ck_three_axis_verdict"),
        CheckConstraint(
            "trend IN ('improving', 'declining', 'stable')", name="ck_three_axis_trend"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity.id", ondelete="CASCADE")
    )
    axis: Mapped[str]  # founder|market|idea
    score: Mapped[float | None]  # 0..100, thesis-relative
    verdict: Mapped[str]  # bull|neutral|bear
    trend: Mapped[str]  # improving|declining|stable
    rationale: Mapped[str | None]
    evidence: Mapped[dict | None] = mapped_column(JSONB)  # cited claim_ids + urls (provenance)
    confidence: Mapped[float | None]
    gaps: Mapped[list | None] = mapped_column(JSONB)  # explicitly flagged missing data
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship(back_populates="axes")


# ── LOOP TABLES (0006) — score_history / memo / trace_step ───────────────────
# The triggered/diligence loop's persistence. score_history is the Founder Score time series
# (one point per recompute that moved the number → the trend arrow); memo is the generated
# investment memo; trace_step records what each screening/memo node did + the evidence it used.
# Relationships are forward-only (no back_populates) so these append cleanly without editing the
# shared Founder / Opportunity / Claim classes above.


class ScoreHistory(Base):
    """One Founder Score point in time. Appended whenever a rescore moves founder.founder_score.

    `trigger_claim_id` links the point to the claim whose mint/rescore caused it (audit); the
    series ordered by created_at yields the trend arrow (see compute_trend, item 3).
    """

    __tablename__ = "score_history"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founder.id", ondelete="CASCADE"))
    score: Mapped[float | None]
    components: Mapped[dict | None] = mapped_column(JSONB)  # founder_score component breakdown
    trigger_claim_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("claim.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    founder: Mapped[Founder] = relationship()


class Memo(Base):
    """The investment memo generated for an opportunity — LLM prose + deterministic guardrails.

    `sections` holds the required memo sections (present-or-gapped); `gaps` lists explicitly-flagged
    missing data / unresolved citations. Never averages the 3 axes — it surfaces their disagreement.
    """

    __tablename__ = "memo"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("opportunity.id", ondelete="CASCADE")
    )
    sections: Mapped[dict | None] = mapped_column(JSONB)  # {section_name: prose}
    recommendation: Mapped[str | None]
    confidence: Mapped[float | None]
    gaps: Mapped[list | None] = mapped_column(JSONB)  # explicit missing-data / unresolved-citation
    quality: Mapped[dict | None] = mapped_column(JSONB)  # eval scorecard (anchors + judge scores)
    generated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    opportunity: Mapped[Opportunity] = relationship()


class TraceStep(Base):
    """One step of the screening/memo flow — agentic traceability (stretch goal #1).

    Plumbing, not LLM: records what a formula/LLM node did (stage, agent, input/output summaries)
    and the evidence_ids it stood on, so a screen or memo can be replayed and audited. Anchored to
    an opportunity and/or a founder (both nullable — a founder-only step has no opportunity yet).
    """

    __tablename__ = "trace_step"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    opportunity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("opportunity.id", ondelete="CASCADE")
    )
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder.id", ondelete="CASCADE")
    )
    stage: Mapped[str]  # screen|score_founder|score_market|score_idea|memo|decide
    agent: Mapped[str | None]
    input: Mapped[dict | None] = mapped_column(JSONB)  # input summary (not the full payload)
    output: Mapped[dict | None] = mapped_column(JSONB)  # output summary
    evidence_ids: Mapped[list | None] = mapped_column(JSONB)  # cited claim/signal ids (provenance)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
