"""domain tables

Companies, founders, opportunities, signals, claims, rejections, traces —
the persistent rows behind the inbound pipeline (mirrors app/models.py).

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-19 00:00:00.000000

"""
from alembic import op  # noqa
import sqlalchemy as sa  # noqa
import sqlmodel.sql.sqltypes  # noqa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "companies",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("founder_ids", JSONB(), nullable=True),
        sa.Column("sector", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("geo", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "founders",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "canonical_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("handles", JSONB(), nullable=True),
        sa.Column("education", JSONB(), nullable=True),
        sa.Column("founder_score", sa.Float(), nullable=True),
        sa.Column("score_history", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "opportunities",
        sa.Column(
            "opportunity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("track", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("company_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("founder_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("stage", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("thesis_json", JSONB(), nullable=True),
        sa.Column("deck_blob_key", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("updated_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["founder_id"], ["founders.id"]),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )
    op.create_table(
        "signals",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("source_url", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("raw_payload", JSONB(), nullable=True),
        sa.Column("entity_hints", JSONB(), nullable=True),
        sa.Column("fetched_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "opportunity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
        ),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.opportunity_id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "claims",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "opportunity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("company_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("category", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("text", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "source_pointer", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("trust_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("trust_confidence", sa.Float(), nullable=True),
        sa.Column("evidence_ids", JSONB(), nullable=True),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.opportunity_id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "rejections",
        sa.Column(
            "opportunity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("reason", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("rejected_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.ForeignKeyConstraint(["opportunity_id"], ["opportunities.opportunity_id"]),
        sa.PrimaryKeyConstraint("opportunity_id"),
    )
    op.create_table(
        "traces",
        sa.Column("id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            "opportunity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False
        ),
        sa.Column("node", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("started_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("ended_at", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("model", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rationale", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("summary", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("evidence_ids", JSONB(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("traces")
    op.drop_table("rejections")
    op.drop_table("claims")
    op.drop_table("signals")
    op.drop_table("opportunities")
    op.drop_table("founders")
    op.drop_table("companies")
