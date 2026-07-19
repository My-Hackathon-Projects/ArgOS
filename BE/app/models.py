"""SQLModel table definitions — the persistent domain tables.

Alembic autogenerate targets ``SQLModel.metadata`` via this module (see
``app/alembic/env.py``). Column specs mirror the pydantic ``*Record``
blueprints in ``app/service/inboud_pipeline/utils/models.py``; ids are
deterministic content hashes assigned by the pipelines, so re-runs are
idempotent (INSERT ... ON CONFLICT DO NOTHING).
"""

from typing import Any

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel


# Generic message
class Message(SQLModel):
    message: str


class Opportunity(SQLModel, table=True):
    """One funnel entry per application/scan hit; stage: received -> queued | rejected."""

    __tablename__ = "opportunities"

    opportunity_id: str = Field(primary_key=True)  # doubles as LangGraph thread_id
    track: str  # inbound | outbound
    company_id: str | None = Field(default=None, foreign_key="companies.id")
    founder_id: str | None = Field(default=None, foreign_key="founders.id")
    stage: str  # received | screened | rejected | queued
    thesis_json: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    deck_blob_key: str | None = None  # MinIO/S3 key of the raw deck PDF
    created_at: str
    updated_at: str


class Signal(SQLModel, table=True):
    """Raw observation, INSERT-only — never UPDATE/DELETE (nothing discarded)."""

    __tablename__ = "signals"

    id: str = Field(primary_key=True)  # content hash — re-uploads are idempotent
    source_type: str  # github | hn | arxiv | deck | application
    source_url: str | None = None
    raw_payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    entity_hints: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    fetched_at: str
    opportunity_id: str | None = Field(
        default=None, foreign_key="opportunities.opportunity_id"
    )  # nullable: outbound scan signals have no opportunity yet


class Founder(SQLModel, table=True):
    """Canonical person; Founder Score persists across applications, never resets."""

    __tablename__ = "founders"

    id: str = Field(primary_key=True)
    canonical_name: str
    handles: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSONB))
    education: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    founder_score: float | None = None  # current snapshot 0..100
    score_history: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSONB))


class Company(SQLModel, table=True):
    """Canonical startup entity."""

    __tablename__ = "companies"

    id: str = Field(primary_key=True)
    name: str
    founder_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
    sector: str | None = None
    geo: str | None = None
    stage: str | None = None


class Claim(SQLModel, table=True):
    """Checkable assertion; trust_* columns filled by the validation pipeline."""

    __tablename__ = "claims"

    id: str = Field(primary_key=True)  # content hash
    opportunity_id: str = Field(foreign_key="opportunities.opportunity_id")
    company_id: str = Field(foreign_key="companies.id")
    category: str  # traction | revenue | team | market
    text: str
    source_pointer: str  # e.g. "deck p.4"
    trust_status: str | None = None  # verified | unverified | contradicted
    trust_confidence: float | None = None
    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB))


class Rejection(SQLModel, table=True):
    """Pre-screen rejection; rejected != deleted — reason stays queryable."""

    __tablename__ = "rejections"

    opportunity_id: str = Field(
        primary_key=True, foreign_key="opportunities.opportunity_id"
    )
    reason: str
    rejected_at: str


class Trace(SQLModel, table=True):
    """Per-node reasoning trail, append-only — behind the UI 'show reasoning' panel."""

    __tablename__ = "traces"

    id: str = Field(primary_key=True)
    opportunity_id: str  # no FK: traces may be written before the opportunity row
    node: str
    started_at: str
    ended_at: str
    duration_ms: float
    model: str | None = None
    rationale: str
    summary: str
    evidence_ids: list[str] = Field(default_factory=list, sa_column=Column(JSONB))
