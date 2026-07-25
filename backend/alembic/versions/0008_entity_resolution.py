"""Entity resolution: structured locations, audit tables, and many-to-many signal attribution.

Squashed from six in-development revisions before release. Two of those were corrections to the
first (entity_merge cascaded away the very audit rows it exists to record), so shipping them
separately would have published a schema we already knew was wrong.

The load-bearing change is `founder_signal`: one source artifact may evidence several people — a
hackathon won by a team of three, a paper with fifteen co-authors. The artifact stays globally
deduplicated while attribution becomes explicit, per-founder and independently scored.
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID

from alembic import op

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Structured, explainable founder location ─────────────────────────────
    for column in ("raw_location", "city_key", "country_code", "location_quality"):
        op.add_column("founder", sa.Column(column, sa.String(), nullable=True))
    op.create_index("ix_founder_city_key", "founder", ["city_key"])

    # ── Source spellings retained after a mention resolves ───────────────────
    op.create_table(
        "founder_alias",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "founder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("raw_name", sa.String(), nullable=False),
        sa.Column("normalized_name", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=True),
        sa.Column(
            "signal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("signal.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("founder_id", "normalized_name", name="uq_founder_alias"),
    )

    # ── Merge audit ──────────────────────────────────────────────────────────
    # A merge DELETES the duplicate founder, so this FK must null out rather than cascade —
    # otherwise the audit row recording the merge is destroyed by the merge itself. The UUID is
    # additionally kept in an FK-free column so the identity survives that null-out.
    op.create_table(
        "entity_merge",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "canonical_founder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "merged_founder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("merged_founder_ref", UUID(as_uuid=True), nullable=True),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("evidence", JSONB(), nullable=True),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    # ── Unresolved person mentions, kept idempotent by fingerprint ───────────
    op.create_table(
        "founder_resolution_review",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("fingerprint", sa.String(), nullable=False),
        sa.Column(
            "founder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("fingerprint", name="uq_founder_resolution_review_fingerprint"),
    )

    # ── One artifact, many founders ──────────────────────────────────────────
    op.create_table(
        "founder_signal",
        sa.Column(
            "founder_id",
            UUID(as_uuid=True),
            sa.ForeignKey("founder.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "signal_id",
            UUID(as_uuid=True),
            sa.ForeignKey("signal.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("attribution_confidence", sa.Float(), nullable=True),
        sa.Column("attribution_method", sa.String(), nullable=True),
        sa.Column(
            "attributed_at", TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_founder_signal_signal_id", "founder_signal", ["signal_id"])

    # Carry existing single-owner attributions across with the confidence they were recorded at.
    # ON CONFLICT DO NOTHING keeps it re-runnable and means a per-founder value can never be
    # overwritten by the legacy signal-level one.
    op.execute(
        """
        INSERT INTO founder_signal (founder_id, signal_id, attribution_confidence,
                                    attribution_method)
        SELECT founder_id, id, resolution_confidence, resolution_method
        FROM signal
        WHERE founder_id IS NOT NULL
        ON CONFLICT (founder_id, signal_id) DO NOTHING
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("entity_merge", "founder_alias", "founder_resolution_review"):
        if bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one():
            raise RuntimeError(
                f"Cannot downgrade 0008 while {table} holds audit data; archive it first."
            )
    # founder_signal is the only record of which founders share an artifact; the legacy
    # signal.founder_id column cannot express a multi-founder attribution.
    shared = bind.execute(
        sa.text(
            "SELECT count(*) FROM (SELECT signal_id FROM founder_signal "
            "GROUP BY signal_id HAVING count(*) > 1) shared_artifacts"
        )
    ).scalar_one()
    if shared:
        raise RuntimeError(
            f"Cannot downgrade 0008: {shared} artifacts are attributed to multiple founders "
            "and that cannot be expressed by signal.founder_id."
        )
    op.drop_index("ix_founder_signal_signal_id", table_name="founder_signal")
    op.drop_table("founder_signal")
    op.drop_table("founder_resolution_review")
    op.drop_table("entity_merge")
    op.drop_table("founder_alias")
    op.drop_index("ix_founder_city_key", table_name="founder")
    for column in ("raw_location", "city_key", "country_code", "location_quality"):
        op.drop_column("founder", column)
