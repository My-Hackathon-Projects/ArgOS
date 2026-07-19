"""loop tables — score_history / memo / trace_step

The triggered/diligence loop's new persistence:
  score_history — Founder Score time series (one row per recompute that moved the score).
  memo         — the investment memo generated for an opportunity.
  trace_step   — agentic traceability: one row per screening/memo node with its evidence.

One migration for all three so the parallel diligence chain never forks. Chains from 0005.

Revision ID: 0006
Revises: 0005
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ── score_history (Founder Score time series) ──
    op.create_table(
        "score_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("score", sa.Float()),
        sa.Column("components", postgresql.JSONB()),
        # The claim whose mint/rescore triggered this point (audit link). SET NULL: keep the
        # history point even if the claim is later deleted.
        sa.Column(
            "trigger_claim_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("claim.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_score_history_founder_created", "score_history", ["founder_id", "created_at"]
    )

    # ── memo (investment memo per opportunity) ──
    op.create_table(
        "memo",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sections", postgresql.JSONB()),
        sa.Column("recommendation", sa.String()),
        sa.Column("confidence", sa.Float()),
        sa.Column("gaps", postgresql.JSONB()),
        sa.Column("quality", postgresql.JSONB()),
        sa.Column(
            "generated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_memo_opportunity", "memo", ["opportunity_id"])

    # ── trace_step (agentic traceability — one row per screen/memo node) ──
    op.create_table(
        "trace_step",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "opportunity_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("opportunity.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "founder_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
        ),
        sa.Column("stage", sa.String(), nullable=False),
        sa.Column("agent", sa.String()),
        sa.Column("input", postgresql.JSONB()),
        sa.Column("output", postgresql.JSONB()),
        sa.Column("evidence_ids", postgresql.JSONB()),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_trace_step_opportunity", "trace_step", ["opportunity_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_trace_step_opportunity", table_name="trace_step")
    op.drop_table("trace_step")
    op.drop_index("ix_memo_opportunity", table_name="memo")
    op.drop_table("memo")
    op.drop_index("ix_score_history_founder_created", table_name="score_history")
    op.drop_table("score_history")
