"""Recompute claim trust from the evidence currently on record.

Trust is noisy-OR over evidence weights, so it is a pure function of the evidence edges. When
those edges change underneath a claim — as when 0015 merged duplicate signal rows and dropped the
redundant citations — the stored score is stale and, in that case, inflated: one artifact cited
twice had been reading as two independent corroborations.

Uses the shared formula in app.claims.trust, never a reimplementation.

Run: uv run python -m app.maintenance.recompute_trust [--dry-run]
"""

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims import trust as trust_mod
from app.db import SessionLocal
from app.models import Claim, ClaimEvidence, Signal


def recompute(db: Session, *, dry_run: bool = True) -> list[dict]:
    changed: list[dict] = []
    for claim in db.execute(select(Claim)).scalars():
        rows = db.execute(
            select(ClaimEvidence, Signal.source)
            .join(Signal, ClaimEvidence.signal_id == Signal.id)
            .where(ClaimEvidence.claim_id == claim.id)
        ).all()
        supports = [e.weight for e, _ in rows if e.stance == "supports" and e.weight is not None]
        refutes = [e.weight for e, _ in rows if e.stance == "refutes" and e.weight is not None]
        sources = sorted({src for _, src in rows})
        score = trust_mod.trust_score(supports, refutes)
        status = trust_mod.derive_status(score, refutes)
        components = trust_mod.trust_components(supports, refutes, sources)
        if claim.trust_score == score and claim.status == status:
            continue
        changed.append(
            {
                "claim_id": str(claim.id),
                "statement": (claim.statement or "")[:70],
                "was": claim.trust_score,
                "now": score,
                "was_n": (claim.trust_components or {}).get("corroboration_n"),
                "now_n": components["corroboration_n"],
            }
        )
        if not dry_run:
            claim.trust_score = score
            claim.status = status
            claim.trust_components = components
    if not dry_run:
        db.commit()
    return changed


def main() -> int:
    dry_run = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        changed = recompute(db, dry_run=dry_run)
        print(f"{'would update' if dry_run else 'updated'} {len(changed)} claim(s)")
        for row in sorted(changed, key=lambda r: (r["now"] or 0) - (r["was"] or 0))[:15]:
            print(
                f"  {row['was']} -> {row['now']}  n {row['was_n']} -> {row['now_n']}  "
                f"{row['statement']}"
            )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
