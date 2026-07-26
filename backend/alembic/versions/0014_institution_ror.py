"""Institutions get a canonical identifier (ROR), like places got geonameid.

`founder.education[].school` is free text, so one university occupied four strings: "Technical
University of Munich" (56), "Technische Universität München" (9), "Technical University of Munich
(TUM)" (5), "Technische Universität München (TUM)" (1) — 71 founders, no way to join them.

`institution` holds the registry record (ROR id + canonical name + country). `institution_alias`
records every string ever seen and what it resolved to, INCLUDING misses: a NULL institution_id
is a negative cache, so a string reaches the ROR API at most once and the unresolved set stays
visible for review rather than being retried forever.

No backfill here — resolution needs the network. `app/maintenance/resolve_institutions.py` does it
as an explicit step, keeping intake independent of a third-party API.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0014"
down_revision: str | None = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "institution",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("ror_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("country_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_institution_ror_id", "institution", ["ror_id"])

    op.create_table(
        "institution_alias",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("alias_key", sa.String(), nullable=False),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column(
            "institution_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("institution.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_institution_alias_key", "institution_alias", ["alias_key"])
    op.create_index("ix_institution_alias_institution", "institution_alias", ["institution_id"])


def downgrade() -> None:
    op.drop_index("ix_institution_alias_institution", table_name="institution_alias")
    op.drop_table("institution_alias")
    op.drop_table("institution")
