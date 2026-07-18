"""initial scraping schema — founder, identity, signal, job_run

Revision ID: 0001
Revises:
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 1536


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "founder",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.String()),
        sa.Column("founder_score", sa.Float()),
        sa.Column("components", postgresql.JSONB()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()")),
    )
    op.execute(
        "CREATE INDEX ix_founder_display_name_trgm ON founder USING gin (display_name gin_trgm_ops)"
    )

    op.create_table(
        "identity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("github", sa.String()),
        sa.Column("twitter", sa.String()),
        sa.Column("linkedin", sa.String()),
        sa.Column("email", sa.String()),
        sa.Column("orcid", sa.String()),
    )

    op.create_table(
        "signal",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("signal_type", sa.String(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="SET NULL"),
        ),
        sa.Column("entity_hint", sa.String()),
        sa.Column("url", sa.String()),
        sa.Column("title", sa.String()),
        sa.Column("summary", sa.String()),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "ingested_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("source_reliability", sa.Float()),
        sa.Column("features", postgresql.JSONB()),
        sa.Column("raw", postgresql.JSONB()),
        sa.Column("embedding", Vector(EMBED_DIM)),
        sa.UniqueConstraint("source", "external_id", name="uq_signal_source_external"),
    )
    op.create_index("ix_signal_founder_id", "signal", ["founder_id"])
    op.create_index("ix_signal_occurred_at", "signal", ["occurred_at"])
    op.execute("CREATE INDEX ix_signal_raw ON signal USING gin (raw)")
    op.execute(
        "CREATE INDEX ix_signal_embedding ON signal USING hnsw (embedding vector_cosine_ops)"
    )

    op.create_table(
        "job_run",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column(
            "started_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("finished_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("new_signals", sa.Integer()),
        sa.Column("errors", sa.String()),
    )


def downgrade() -> None:
    op.drop_table("job_run")
    op.drop_table("signal")
    op.drop_table("identity")
    op.drop_table("founder")
