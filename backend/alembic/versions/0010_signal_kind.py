"""Add signal.kind — explicit provenance for founder vs market artifacts.

The market writer (`app/market/persist.py`) mints one `web` signal per cited hit and never
attributes it in `founder_signal`, deliberately keeping it out of the founder-claim pipeline.
Nothing recorded that intent: "is this a market artifact?" was answerable only by a NOT EXISTS
against `founder_signal` — an implicit rule, invisible to readers and unenforceable at write time.

Backfill is unambiguous by measurement. In the development database:
  - 180 signals carry no founder attribution,
  - the same 180 are exactly those whose signal_type is one the market writer mints
    (market_size|market_trend|competitor|benchmark|funding|market),
  - 0 unattributed signals fall outside that set,
  - 0 opportunity-anchored claims cite a signal outside that set.
The two candidate rules agree exactly, so the edge rule is used (it *is* the invariant) and the
signal_type agreement is re-checked here as a guard before the column is made NOT NULL.

The cross-table rule (kind='market' => no founder_signal row) is not a CHECK: Postgres CHECK
cannot reference another table. It is enforced at the single writer and asserted in
tests/test_signal_kind.py. Only the value domain is constrained here.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None

_MARKET_TYPES = "('market_size', 'market_trend', 'competitor', 'benchmark', 'funding', 'market')"


def upgrade() -> None:
    # No server_default, deliberately: every writer must state provenance explicitly, and a
    # default would silently file a forgotten market artifact under 'founder'. Added nullable,
    # backfilled below, then sealed NOT NULL.
    op.add_column("signal", sa.Column("kind", sa.String(), nullable=True))

    bind = op.get_bind()
    # Guard: the edge rule and the signal_type rule must still describe the same population.
    # If discovery has since minted an unattributed founder artifact, the rules diverge and the
    # backfill would silently mislabel it as market evidence.
    divergent = bind.execute(
        sa.text(
            "SELECT count(*) FROM signal s "
            "WHERE NOT EXISTS (SELECT 1 FROM founder_signal f WHERE f.signal_id = s.id) "
            f"AND s.signal_type NOT IN {_MARKET_TYPES}"
        )
    ).scalar_one()
    if divergent:
        raise RuntimeError(
            f"Refusing to backfill signal.kind: {divergent} unattributed signals are not of a "
            "market-minted signal_type. Classify them explicitly before migrating."
        )

    op.execute(
        "UPDATE signal s SET kind = 'market' "
        "WHERE NOT EXISTS (SELECT 1 FROM founder_signal f WHERE f.signal_id = s.id)"
    )
    op.execute("UPDATE signal SET kind = 'founder' WHERE kind IS NULL")
    op.alter_column("signal", "kind", nullable=False)
    op.create_check_constraint("ck_signal_kind", "signal", "kind IN ('founder', 'market')")
    op.create_index("ix_signal_kind", "signal", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_signal_kind", table_name="signal")
    op.drop_constraint("ck_signal_kind", "signal", type_="check")
    op.drop_column("signal", "kind")
