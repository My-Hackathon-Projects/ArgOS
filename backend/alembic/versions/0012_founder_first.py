"""Founder-first as a constraint: opportunity.founder_id NOT NULL.

The product rule — a deal is a person plus what they are building, and the Founder Score is
per-person and follows them across startups — was enforced nowhere. `founder_id` was nullable,
`POST /opportunities` accepted a missing founder, and the market path could mint a company-first
deal from a bare dict. The dev DB collected three founderless rows through those holes.

This migration REFUSES to run while any founderless opportunity remains, rather than deciding
their fate silently. Deleting a deal destroys its claims, axes and traces (all ON DELETE CASCADE);
attaching an arbitrary founder fabricates a relationship in a system whose entire value is
provenance. Both are decisions for a human, so the migration reports the rows and stops.

The FK becomes RESTRICT: with NOT NULL, ON DELETE SET NULL is self-contradictory (it would try to
write a NULL the column forbids), so removing a founder who still has deals must fail loudly
instead of silently orphaning them.
"""

import sqlalchemy as sa

from alembic import op

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    orphans = bind.execute(
        sa.text(
            "SELECT id, company_name, status FROM opportunity WHERE founder_id IS NULL "
            "ORDER BY company_name"
        )
    ).all()
    if orphans:
        listed = "; ".join(f"{o.company_name or '(unnamed)'} [{o.status}] {o.id}" for o in orphans)
        raise RuntimeError(
            f"Refusing to make opportunity.founder_id NOT NULL: {len(orphans)} founderless "
            f"deal(s) still exist -> {listed}. Each must be explicitly resolved first — map a "
            "founder, or delete the deal knowing its claims/axes/traces cascade with it."
        )

    op.alter_column("opportunity", "founder_id", nullable=False)
    op.drop_constraint("opportunity_founder_id_fkey", "opportunity", type_="foreignkey")
    op.create_foreign_key(
        "opportunity_founder_id_fkey",
        "opportunity",
        "founder",
        ["founder_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint("opportunity_founder_id_fkey", "opportunity", type_="foreignkey")
    op.create_foreign_key(
        "opportunity_founder_id_fkey",
        "opportunity",
        "founder",
        ["founder_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.alter_column("opportunity", "founder_id", nullable=True)
