"""sourcing layer — founder/identity/signal enrichment + investment_thesis + sourcing_channel

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-19

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS fuzzystrmatch")

    # ── founder: person attributes + outbound lifecycle + uncertainty ──
    op.add_column("founder", sa.Column("first_name", sa.String()))
    op.add_column("founder", sa.Column("last_name", sa.String()))
    op.add_column("founder", sa.Column("dob", sa.Date()))
    op.add_column("founder", sa.Column("city", sa.String()))
    op.add_column("founder", sa.Column("occupation", sa.String()))
    op.add_column("founder", sa.Column("current_company", sa.String()))
    op.add_column("founder", sa.Column("education", postgresql.JSONB()))
    op.add_column(
        "founder",
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'candidate'")),
    )
    op.add_column("founder", sa.Column("discovery_confidence", sa.Float()))
    op.add_column("founder", sa.Column("first_discovered_at", sa.TIMESTAMP(timezone=True)))
    op.add_column("founder", sa.Column("last_checked_at", sa.TIMESTAMP(timezone=True)))
    op.create_check_constraint(
        "ck_founder_status", "founder", "status IN ('candidate', 'needs_review', 'confirmed')"
    )

    # ── identity: extra strong keys ──
    op.add_column("identity", sa.Column("website", sa.String()))
    op.add_column("identity", sa.Column("other_socials", postgresql.JSONB()))

    # ── signal: web dedup + resolution provenance ──
    op.add_column("signal", sa.Column("canonical_url", sa.String()))
    op.add_column("signal", sa.Column("content_hash", sa.String()))
    op.add_column("signal", sa.Column("resolution_confidence", sa.Float()))
    op.add_column("signal", sa.Column("resolution_method", sa.String()))
    op.add_column("signal", sa.Column("sources_seen", postgresql.JSONB()))
    # Global cross-source dedup: one signal per artifact URL / content hash.
    op.execute(
        "CREATE UNIQUE INDEX uq_signal_canonical_url ON signal (canonical_url) "
        "WHERE canonical_url IS NOT NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_signal_content_hash ON signal (content_hash) "
        "WHERE content_hash IS NOT NULL"
    )

    # ── investment_thesis ──
    op.create_table(
        "investment_thesis",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String()),
        sa.Column("industries", postgresql.ARRAY(sa.String())),
        sa.Column("geo", postgresql.ARRAY(sa.String())),
        sa.Column("stage", postgresql.ARRAY(sa.String())),
        sa.Column("keywords", postgresql.ARRAY(sa.String())),
        sa.Column("founder_preferences", postgresql.JSONB()),
        sa.Column("check_size", sa.Float()),
        sa.Column("ownership", sa.Float()),
        sa.Column("risk", sa.String()),
        sa.Column("free_text", sa.String()),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_thesis_one_default ON investment_thesis (is_default) "
        "WHERE is_default = true"
    )

    # ── sourcing_channel ──
    op.create_table(
        "sourcing_channel",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("type", sa.String()),
        sa.Column("domain", sa.String()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("thesis_relevant", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("yield_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("quality_score", sa.Float()),
        sa.Column("last_success_at", sa.TIMESTAMP(timezone=True)),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_sourcing_channel_name", "sourcing_channel", ["name"], unique=True)


def downgrade() -> None:
    op.drop_table("sourcing_channel")
    op.execute("DROP INDEX IF EXISTS uq_thesis_one_default")
    op.drop_table("investment_thesis")
    op.execute("DROP INDEX IF EXISTS uq_signal_content_hash")
    op.execute("DROP INDEX IF EXISTS uq_signal_canonical_url")
    for col in (
        "sources_seen",
        "resolution_method",
        "resolution_confidence",
        "content_hash",
        "canonical_url",
    ):
        op.drop_column("signal", col)
    op.drop_column("identity", "other_socials")
    op.drop_column("identity", "website")
    op.drop_constraint("ck_founder_status", "founder", type_="check")
    for col in (
        "last_checked_at",
        "first_discovered_at",
        "discovery_confidence",
        "status",
        "education",
        "current_company",
        "occupation",
        "city",
        "dob",
        "last_name",
        "first_name",
    ):
        op.drop_column("founder", col)
