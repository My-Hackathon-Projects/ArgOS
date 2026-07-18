"""Minimal scraping-core schema. The shared contract every connector writes into.

Only the tables the sourcing pipeline needs right now:
founder + identity (entity resolution), signal (ingested events), job_run (cron ops).
Scoring / opportunity / claim / memo tables come with later features.
"""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, UniqueConstraint, func
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
