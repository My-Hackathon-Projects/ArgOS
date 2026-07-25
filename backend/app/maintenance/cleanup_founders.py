"""Restore the founder-first invariants in an existing database.

Discovery ran for days with a resolver that minted a new Founder row for every unresolved
mention and a gate that admitted events and GitHub organisations. This repairs the residue:

  1. non-person founders (events, orgs, bare handles) and any artifact left with no owner
  2. founders carrying no signal at all (including rows committed by the old test suite)
  3. duplicate people, merged through the audited reconcile path
  4. opportunities with no founder, which founder-first forbids

Usage:
    uv run python -m app.maintenance.cleanup_founders --dry-run
    uv run python -m app.maintenance.cleanup_founders --apply
"""

import argparse
from collections import defaultdict

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.entity_resolution import compact_person_name, is_person_name
from app.models import Founder, Opportunity, Signal, founder_signal
from app.reconcile import find_merge_candidates, merge_founders


def _non_person_founders(db: Session) -> list[Founder]:
    return [f for f in db.execute(select(Founder)).scalars() if not is_person_name(f.display_name)]


def _founders_without_signals(db: Session) -> list[Founder]:
    return list(
        db.execute(
            select(Founder)
            .outerjoin(founder_signal, founder_signal.c.founder_id == Founder.id)
            .where(founder_signal.c.founder_id.is_(None))
        )
        .scalars()
        .all()
    )


def _orphaned_signal_ids(db: Session) -> list:
    """Founder-sourced artifacts left with no owner. Market signals are excluded: they belong
    to a thesis, not a person, and legitimately have no founder."""
    return list(
        db.execute(
            select(Signal.id)
            .outerjoin(founder_signal, founder_signal.c.signal_id == Signal.id)
            .where(
                founder_signal.c.signal_id.is_(None),
                Signal.source.notin_(("crunchbase",)),
                Signal.signal_type.notin_(
                    ("market_size", "market_trend", "competitor", "benchmark", "funding")
                ),
            )
        )
        .scalars()
        .all()
    )


def _duplicate_groups(db: Session) -> dict[str, list[Founder]]:
    groups: dict[str, list[Founder]] = defaultdict(list)
    for founder in db.execute(
        select(Founder).order_by(Founder.first_discovered_at.nullsfirst(), Founder.id)
    ).scalars():
        key = compact_person_name(founder.display_name)
        if key:
            groups[key].append(founder)
    return {key: rows for key, rows in groups.items() if len(rows) > 1}


def _is_safe_merge(result) -> bool:
    """Only collapse two rows on positive evidence.

    A ``review`` verdict with conflicts means the identities contradict each other — the rows
    are different people (or one carries a bad identity), so merging them would destroy a real
    person. Uncertain-but-unconflicted pairs are left alone for a human rather than guessed at.
    """
    return result.decision == "merge" and not result.conflicts


def cleanup(db: Session, *, dry_run: bool = True) -> dict:
    report: dict = {"dry_run": dry_run}

    non_persons = _non_person_founders(db)
    report["non_person_founders"] = [f.display_name for f in non_persons]
    if not dry_run and non_persons:
        db.execute(delete(Founder).where(Founder.id.in_([f.id for f in non_persons])))
        db.flush()

    groups = _duplicate_groups(db)
    report["duplicate_groups_before"] = {k: len(v) for k, v in groups.items()}
    merged = []
    if not dry_run:
        # Rebuild candidates after each merge: a three-row cluster would otherwise reference
        # a row the previous merge already deleted.
        while True:
            pair = next(
                (c for c in find_merge_candidates(db) if _is_safe_merge(c[2])),
                None,
            )
            if pair is None:
                break
            canonical, duplicate, result = pair
            merged.append(
                {
                    "canonical": canonical.display_name,
                    "duplicate": duplicate.display_name,
                    "decision": result.decision,
                    "confidence": result.confidence,
                    "reasons": list(result.reasons),
                }
            )
            merge_founders(
                db,
                canonical,
                duplicate,
                method=f"cleanup_{result.decision}",
                confidence=result.confidence,
                evidence=result.evidence,
                commit=False,
            )
    else:
        merged = [
            {
                "canonical": left.display_name,
                "duplicate": right.display_name,
                "decision": result.decision,
                "confidence": result.confidence,
                "reasons": list(result.reasons),
            }
            for left, right, result in find_merge_candidates(db)
            if _is_safe_merge(result)
        ]
    report["merges"] = merged

    # Runs after the merges: a duplicate may have held every signal for the person.
    orphan_founders = _founders_without_signals(db)
    report["founders_without_signals"] = [f.display_name for f in orphan_founders]
    if not dry_run and orphan_founders:
        db.execute(delete(Founder).where(Founder.id.in_([f.id for f in orphan_founders])))
        db.flush()

    orphan_signals = _orphaned_signal_ids(db)
    report["orphaned_founder_signals"] = len(orphan_signals)
    if not dry_run and orphan_signals:
        db.execute(delete(Signal).where(Signal.id.in_(orphan_signals)))
        db.flush()

    founderless = (
        db.execute(select(Opportunity).where(Opportunity.founder_id.is_(None))).scalars().all()
    )
    report["opportunities_without_founder"] = [
        {"company": o.company_name, "status": o.status} for o in founderless
    ]

    if not dry_run:
        db.commit()
    report["remaining"] = {
        "founders": db.scalar(select(func.count()).select_from(Founder)),
        "signals": db.scalar(select(func.count()).select_from(Signal)),
        "duplicate_groups": len(_duplicate_groups(db)),
        "founders_without_signals": len(_founders_without_signals(db)),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True)
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        report = cleanup(db, dry_run=not args.apply)
    finally:
        db.close()
    import json

    print(json.dumps(report, indent=2, default=str, ensure_ascii=False))


if __name__ == "__main__":
    main()
