"""diligence — company / opportunity / founder_company / three_axis + claim.opportunity_id

The market-research agent's shared seam. Adds the diligence entities and widens `claim` so a
claim can be anchored to an opportunity (company/market-level) instead of a founder (person-level).
Market claims set opportunity_id + founder_id NULL so they never roll into the Founder Score.

Revision ID: 0005
Revises: 0004
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── company (optional venture) ──
    op.create_table(
        "company",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String()),
        sa.Column("website", sa.String()),
        sa.Column("sector", sa.String()),
        sa.Column("geo", sa.String()),
        sa.Column("description", sa.String()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ── founder_company (co-founders / serial founders) ──
    op.create_table(
        "founder_company",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String()),
        sa.UniqueConstraint("founder_id", "company_id", name="uq_founder_company"),
    )

    # ── opportunity (the deal — founder + optional company + idea) ──
    op.create_table(
        "opportunity",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "company_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("company.id", ondelete="SET NULL"),
        ),
        sa.Column("company_name", sa.String()),
        sa.Column("idea", sa.String()),
        sa.Column("sector", sa.String()),
        sa.Column("geo", sa.String()),
        sa.Column("source", sa.String()),
        sa.Column("thesis_match", sa.Float()),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'screening'")),
        sa.Column("decision", sa.String()),
        sa.Column("first_signal_at", sa.TIMESTAMP(timezone=True)),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "status IN ('screening', 'diligence', 'decided', 'rejected')",
            name="ck_opportunity_status",
        ),
    )
    op.create_index("ix_opportunity_founder", "opportunity", ["founder_id"])

    # ── three_axis (3 rows per opportunity, never averaged) ──
    op.create_table(
        "three_axis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("axis", sa.String(), nullable=False),
        sa.Column("score", sa.Float()),
        sa.Column("verdict", sa.String(), nullable=False),
        sa.Column("trend", sa.String(), nullable=False),
        sa.Column("rationale", sa.String()),
        sa.Column("evidence", postgresql.JSONB()),
        sa.Column("confidence", sa.Float()),
        sa.Column("gaps", postgresql.JSONB()),
        sa.Column(
            "created_at",
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
        sa.UniqueConstraint("opportunity_id", "axis", name="uq_three_axis_opportunity_axis"),
        sa.CheckConstraint("axis IN ('founder', 'market', 'idea')", name="ck_three_axis_axis"),
        sa.CheckConstraint("verdict IN ('bull', 'neutral', 'bear')", name="ck_three_axis_verdict"),
        sa.CheckConstraint(
            "trend IN ('improving', 'declining', 'stable')", name="ck_three_axis_trend"
        ),
    )

    # ── claim: widen to allow company/market-level (opportunity-anchored) claims ──
    op.alter_column("claim", "founder_id", nullable=True)
    op.add_column(
        "claim",
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
        ),
    )
    op.create_check_constraint(
        "ck_claim_owner", "claim", "founder_id IS NOT NULL OR opportunity_id IS NOT NULL"
    )
    op.create_index("ix_claim_opportunity_category", "claim", ["opportunity_id", "category"])
    # Idempotent re-runs: one claim per (opportunity, dedup_key) when a key exists.
    op.execute(
        "CREATE UNIQUE INDEX uq_claim_opportunity_dedup ON claim (opportunity_id, dedup_key) "
        "WHERE opportunity_id IS NOT NULL AND dedup_key IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_claim_opportunity_dedup")
    op.drop_index("ix_claim_opportunity_category", table_name="claim")
    op.drop_constraint("ck_claim_owner", "claim", type_="check")
    op.drop_column("claim", "opportunity_id")
    op.alter_column("claim", "founder_id", nullable=False)
    op.drop_table("three_axis")
    op.drop_index("ix_opportunity_founder", table_name="opportunity")
    op.drop_table("opportunity")
    op.drop_table("founder_company")
    op.drop_table("company")
