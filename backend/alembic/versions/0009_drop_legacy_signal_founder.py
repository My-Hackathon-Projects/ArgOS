"""Drop the legacy single-owner signal.founder_id column.

Attribution moved to `founder_signal` in 0008, and every application read followed it. The old
column kept being written by reconciliation while no business code read it, so the two
representations could only drift — a trap for the next writer, and a second answer to
"whose signal is this".

Safe by measurement: in the development database every (founder_id, signal) pair the column held
was already present in founder_signal (0 rows set-but-missing), while 646 attributions existed
that the column could not express at all. The upgrade re-checks that invariant before dropping.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    missing = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM signal s WHERE s.founder_id IS NOT NULL AND NOT EXISTS ("
                "SELECT 1 FROM founder_signal fs "
                "WHERE fs.signal_id = s.id AND fs.founder_id = s.founder_id)"
            )
        )
        .scalar_one()
    )
    if missing:
        raise RuntimeError(
            f"Refusing to drop signal.founder_id: {missing} attributions exist only on the legacy "
            "column. Backfill founder_signal from it first (see 0008)."
        )
    op.drop_index("ix_signal_founder_id", table_name="signal")
    op.drop_column("signal", "founder_id")


def downgrade() -> None:
    op.add_column("signal", sa.Column("founder_id", sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "signal_founder_id_fkey", "signal", "founder", ["founder_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_signal_founder_id", "signal", ["founder_id"])
    # Restores only unambiguous ownership. A shared artifact has no single owner to restore, so
    # it is deliberately left NULL rather than silently attributed to an arbitrary founder.
    op.execute(
        """
        UPDATE signal s SET founder_id = sole.founder_id
        FROM (SELECT signal_id, min(founder_id::text)::uuid AS founder_id
              FROM founder_signal GROUP BY signal_id HAVING count(*) = 1) sole
        WHERE sole.signal_id = s.id
        """
    )
