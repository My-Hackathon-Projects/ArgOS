"""claims layer — claim + claim_evidence (M:N to signal, with stance + trust)

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EMBED_DIM = 1536


def upgrade() -> None:
    op.create_table(
        "claim",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("statement", sa.String(), nullable=False),
        sa.Column("attributes", postgresql.JSONB()),
        sa.Column("trust_score", sa.Float()),
        sa.Column("trust_components", postgresql.JSONB()),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'unverified'")),
        sa.Column("embedding", Vector(EMBED_DIM)),
        sa.Column("dedup_key", sa.String()),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('unverified', 'verified', 'contradicted', 'needs_review')",
            name="ck_claim_status",
        ),
    )
    op.create_index("ix_claim_founder_category", "claim", ["founder_id", "category"])
    op.create_index("ix_claim_status", "claim", ["status"])
    # Cheap deterministic dedup: one claim per (founder, dedup_key) when a key exists.
    op.execute(
        "CREATE UNIQUE INDEX uq_claim_founder_dedup ON claim (founder_id, dedup_key) "
        "WHERE dedup_key IS NOT NULL"
    )
    # kNN over claim statements → the incremental match step (attach vs mint).
    op.execute("CREATE INDEX ix_claim_embedding ON claim USING hnsw (embedding vector_cosine_ops)")

    op.create_table(
        "claim_evidence",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claim.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "signal_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("signal.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stance", sa.String(), nullable=False),
        sa.Column("weight", sa.Float()),
        sa.Column("extraction_conf", sa.Float()),
        sa.Column("rationale", sa.String()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("claim_id", "signal_id", name="uq_claim_evidence_edge"),
        sa.CheckConstraint("stance IN ('supports', 'refutes')", name="ck_evidence_stance"),
    )
    # Reverse lookup: "which claims does this signal back" (provenance + rescore fan-out).
    op.create_index("ix_claim_evidence_signal", "claim_evidence", ["signal_id"])


def downgrade() -> None:
    op.drop_table("claim_evidence")
    op.drop_table("claim")
