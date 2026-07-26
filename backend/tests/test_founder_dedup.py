"""Regressions for the duplicate-founder defect found in the dev database.

Every case here is modelled on a real pair discovery produced (12 duplicate pairs across 3 runs).
The shared shape: an existing founder is re-discovered, the resolver cannot prove identity, and a
second Founder row is minted. Founder Score is per-person and must never fragment, so the
invariant under test is: re-discovering a known person NEVER increases the founder count.
"""

from datetime import UTC, datetime

from helpers import unique_suffix
from sqlalchemy import func, select, text

from app.db import SessionLocal
from app.models import Founder, Identity, founder_signal
from app.sourcing.persist import (
    _FOUNDER_WRITER_LOCK,
    persist_delivery,
    resolve_or_create_founder,
)


def _artifact(suffix: str, n: int = 1) -> dict:
    url = f"https://arxiv.test/abs/{suffix}-{n}"
    return {
        "source": "arxiv",
        "signal_type": "publication",
        "canonical_url": url,
        "content_hash": f"hash-{suffix}-{n}",
        "url": url,
        "title": f"Paper {n}",
        "summary": "A paper.",
        "source_reliability": 0.8,
        "resolution_confidence": 0.7,
        "resolution_method": "fuzzy",
        "sources_seen": ["arxiv"],
    }


def _candidate(name: str, signals: list[dict], **kw) -> dict:
    return {"display_name": name, "status": "candidate", "signals": signals, **kw}


def _count(db, name_fragment: str) -> int:
    return db.scalar(
        select(func.count())
        .select_from(Founder)
        .where(Founder.display_name.contains(name_fragment))
    )


def test_rediscovery_with_shared_artifact_resolves_to_existing_founder() -> None:
    """The Mario Krenn / Philipp Hennig case: duplicate shared 2-3 canonical artifacts."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Mario Krenn {suffix}"
        shared = _artifact(suffix, 1)

        persist_delivery(db, [_candidate(name, [shared])], commit=False)
        # Re-discovery: same person, no identity derived this round, same artifact seen again.
        result = persist_delivery(
            db, [_candidate(name, [shared, _artifact(suffix, 2)])], commit=False
        )

        assert _count(db, suffix) == 1, "re-discovery must not mint a second founder"
        assert result["new_founders"] == 0
        assert result["resolved_to_existing"] == 1
    finally:
        db.rollback()
        db.close()


def test_rediscovery_with_newly_found_identity_enriches_existing_founder() -> None:
    """The Taylor T. Johnson case: original had no identity, the duplicate carried the LinkedIn."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Taylor Johnson {suffix}"

        persist_delivery(db, [_candidate(name, [_artifact(suffix, 1)])], commit=False)
        later = _candidate(name, [_artifact(suffix, 2)])
        later["identity"] = {"linkedin": f"https://www.linkedin.com/in/taylor-{suffix}"}
        persist_delivery(db, [later], commit=False)

        assert _count(db, suffix) == 1, "a newly discovered identity must enrich, not duplicate"
        founder = db.scalar(select(Founder).where(Founder.display_name.contains(suffix)))
        assert founder is not None
        stored = db.scalars(
            select(Identity.linkedin).where(Identity.founder_id == founder.id)
        ).all()
        assert any(value and suffix in value for value in stored), (
            "the newly discovered LinkedIn must be persisted on the existing founder"
        )
    finally:
        db.rollback()
        db.close()


def test_two_mentions_of_one_person_in_one_delivery_create_one_founder() -> None:
    """autoflush=False meant an Identity added earlier in the same loop was invisible."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Weiming Xiang {suffix}"
        handle = f"wxiang-{suffix}"
        first = _candidate(name, [_artifact(suffix, 1)])
        first["identity"] = {"github": handle}
        second = _candidate(name, [_artifact(suffix, 2)])
        second["identity"] = {"github": handle}

        persist_delivery(db, [first, second], commit=False)

        assert _count(db, suffix) == 1
    finally:
        db.rollback()
        db.close()


def test_replaying_the_same_delivery_is_idempotent() -> None:
    """Discovery re-runs on a similar seed every cycle; the founder count must be stable."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        delivery = [
            _candidate(f"Diego Lopez {suffix}", [_artifact(suffix, 1)]),
            _candidate(f"Nathaniel Hamilton {suffix}", [_artifact(suffix, 2)]),
        ]

        persist_delivery(db, delivery, commit=False)
        before = _count(db, suffix)
        persist_delivery(db, delivery, commit=False)
        persist_delivery(db, delivery, commit=False)

        assert before == 2
        assert _count(db, suffix) == 2, "replaying a delivery must not grow the founder table"
    finally:
        db.rollback()
        db.close()


def test_conflicting_strong_identities_never_merge_two_people() -> None:
    """Homonym safety: same name, but each side has a different LinkedIn -> two people."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Xiaodong Yang {suffix}"
        first = _candidate(name, [_artifact(suffix, 1)])
        first["identity"] = {"linkedin": f"https://www.linkedin.com/in/xy-a-{suffix}"}
        second = _candidate(name, [_artifact(suffix, 2)])
        second["identity"] = {"linkedin": f"https://www.linkedin.com/in/xy-b-{suffix}"}

        persist_delivery(db, [first], commit=False)
        persist_delivery(db, [second], commit=False)

        assert _count(db, suffix) == 2, "conflicting identities must not collapse into one person"
    finally:
        db.rollback()
        db.close()


def test_a_tie_between_two_candidates_resolves_to_the_earliest_discovered_person() -> None:
    """Which person a mention attaches to must not depend on Postgres' physical row order.

    `resolve_candidates` breaks ties with a strict `>`, so the first candidate it is handed wins —
    and the candidate query had no ORDER BY. Two equally-good matches would then resolve to
    whichever row the scan returned first, which is free to change after any UPDATE or VACUUM: the
    same input attaches to a different human on a later run, and Founder Score follows it there.
    The rule is the same one `find_merge_candidates` already uses — the person we knew first.

    The later-discovered row is inserted first here, so insertion order and discovery order
    disagree and only an explicit ordering can satisfy this.
    """
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Grace Hopper {suffix}"
        later = Founder(
            display_name=name,
            city="Munich",
            first_discovered_at=datetime(2026, 5, 1, tzinfo=UTC),
        )
        earlier = Founder(
            display_name=name,
            city="Munich",
            first_discovered_at=datetime(2020, 1, 1, tzinfo=UTC),
        )
        db.add_all([later, earlier])
        db.flush()
        earliest_id = earlier.id

        persist_delivery(
            db,
            [_candidate(name, [_artifact(suffix, 1)], city="Munich")],
            commit=False,
        )

        assert _count(db, suffix) == 2, "the mention must attach, not mint a third row"
        owner = db.scalar(
            select(founder_signal.c.founder_id).where(
                founder_signal.c.founder_id.in_([later.id, earliest_id])
            )
        )
        assert owner == earliest_id
    finally:
        db.rollback()
        db.close()


def test_resolving_a_founder_takes_the_writer_lock_itself() -> None:
    """Two processes that both read "nobody matches" both create the person.

    The guard used to sit on the discovery cron, which left the inbound deck intake — same
    resolver, called from a request handler — racing it with no lock at all. Owning the lock in
    the writer is what makes every caller safe, including ones not written yet.
    """
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        resolve_or_create_founder(db, {"display_name": f"Radia Perlman {suffix}"})

        held = db.scalar(
            text(
                "SELECT count(*) FROM pg_locks WHERE locktype = 'advisory' "
                "AND objid = :lock_id AND pid = pg_backend_pid() AND granted"
            ),
            {"lock_id": _FOUNDER_WRITER_LOCK},
        )
        assert held == 1
    finally:
        db.rollback()
        db.close()


def test_every_persisted_founder_has_at_least_one_signal() -> None:
    """Founder-first invariant: a person with no evidence has no reason to exist."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        persist_delivery(
            db,
            [
                _candidate(f"With Evidence {suffix}", [_artifact(suffix, 1)]),
                _candidate(f"No Evidence {suffix}", []),
            ],
            commit=False,
        )

        orphans = db.scalars(
            select(Founder.display_name)
            .outerjoin(founder_signal, founder_signal.c.founder_id == Founder.id)
            .where(Founder.display_name.contains(suffix), founder_signal.c.founder_id.is_(None))
        ).all()
        assert orphans == []
    finally:
        db.rollback()
        db.close()
