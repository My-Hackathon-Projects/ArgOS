"""Minimal scraping-core schema. The shared contract every connector writes into.

Sourcing core + the claims layer:
founder + identity (entity resolution), signal (ingested events), job_run (cron ops),
claim + claim_evidence (corroborated assertions → the rescore seam).
Opportunity / memo / weight_profile tables come with later features.

See docs/claims-layer.md for how claims relate to signals + scoring.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

EMBED_DIM = 1536  # text-embedding-3-small


class Founder(Base):
    """The person. One row per real human; the Founder Score persists here across startups."""

    __tablename__ = "founder"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name: Mapped[str | None]
    founder_score: Mapped[float | None]
    components: Mapped[dict | None] = mapped_column(JSONB)
    updated_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # ── Planned enrichment (promote to columns when a source populates them) ──
    # first_name / last_name       structured split of display_name
    # headline / bio               one-line role + longer summary
    # location                     city / country (feeds thesis geo filter)
    # education     jsonb          [{school, degree, field, year}]
    # work_history  jsonb          [{company, title, start, end}]  — prior jobs
    # resume_url / personal_site   links
    # avatar_url

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

    founder: Mapped[Founder] = relationship(back_populates="identities")


class Signal(Base):
    """One polymorphic table for every source. (source, external_id) unique → idempotent poll."""

    __tablename__ = "signal"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_signal_source_external"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str]  # github|arxiv|devpost|producthunt|hn|synthetic|inbound
    signal_type: Mapped[str]  # commit|repo_release|paper|hackathon_win|launch|post|deck
    external_id: Mapped[str]  # source-native id
    founder_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("founder.id", ondelete="SET NULL")
    )
    entity_hint: Mapped[str | None]  # raw handle/name pre-resolution ("github:torvalds")
    url: Mapped[str | None]
    title: Mapped[str | None]
    summary: Mapped[str | None]  # short normalized text → feed + embedding
    occurred_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    ingested_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    source_reliability: Mapped[float | None]  # per-source prior 0..1
    features: Mapped[dict | None] = mapped_column(JSONB)  # LLM-extracted once, cached
    raw: Mapped[dict | None] = mapped_column(JSONB)  # full original payload, nothing discarded
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))

    founder: Mapped[Founder | None] = relationship(back_populates="signals")
    claim_links: Mapped[list["ClaimEvidence"]] = relationship(back_populates="signal")


class JobRun(Base):
    """One row per connector poll → the ops/monitoring panel."""

    __tablename__ = "job_run"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source: Mapped[str]
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    new_signals: Mapped[int | None]
    errors: Mapped[str | None]


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
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    founder_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("founder.id", ondelete="CASCADE"))
    # opportunity_id lands when the inbound/diligence side adds the opportunity table.
    category: Mapped[str]  # publication|technical_skill|achievement|traction|revenue|team|market|...
    statement: Mapped[str]  # canonical NL claim, shown in memo/UI
    attributes: Mapped[dict | None] = mapped_column(JSONB)  # structured {venue, year, metric, value}
    trust_score: Mapped[float | None]  # deterministic formula over evidence (== confidence level)
    trust_components: Mapped[dict | None] = mapped_column(JSONB)  # formula inputs, auditable receipts
    status: Mapped[str] = mapped_column(server_default=text("'unverified'"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM))  # statement -> matching kNN
    dedup_key: Mapped[str | None]  # optional deterministic key -> cheap exact attach, skips the LLM
    first_seen_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )  # bumps on evidence/trust change -> the rescore trigger

    founder: Mapped[Founder] = relationship(back_populates="claims")
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
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now())

    claim: Mapped[Claim] = relationship(back_populates="evidence")
    signal: Mapped[Signal] = relationship(back_populates="claim_links")
