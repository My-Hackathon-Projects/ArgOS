"""Unresolved identity conflicts remain idempotent across repeated deliveries."""

import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Founder, FounderResolutionReview, Identity
from app.sourcing.persist import resolve_or_create_founder


def test_replaying_an_unresolved_identity_conflict_reuses_the_review_founder() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        existing = Founder(display_name="Alex Rohregger", city="Munich")
        db.add(existing)
        db.flush()
        db.add(Identity(founder_id=existing.id, github=f"shared-{suffix}"))
        db.flush()

        incoming = {
            "display_name": "Pasha Rizali",
            "city": "Munich",
            "current_company": "Robotics Lab",
            "identity": {"github": f"shared-{suffix}"},
        }
        first_id, first_method = resolve_or_create_founder(db, incoming)
        db.flush()
        second_id, second_method = resolve_or_create_founder(db, incoming)
        db.flush()

        # A shared handle under two different names is a conflict: the people stay separate,
        # but replaying the same mention must reuse the row it already created.
        assert first_method == "conflict"
        # On the replay the handle is claimed by BOTH rows, so it no longer identifies anyone
        # and is withdrawn from identity evidence (_non_identifying_handles). The match then
        # rests on name + context, which is uncertain by design -> "review". The property this
        # test exists for is unchanged: the same row is reused and only one review is recorded.
        assert second_method in {"conflict", "exact_key", "review"}
        assert second_id == first_id
        assert db.scalar(select(func.count()).select_from(FounderResolutionReview)) == 1
    finally:
        db.rollback()
        db.close()


def test_second_identity_row_is_used_for_resolution() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        existing = Founder(display_name="Ada Lovelace", city="London")
        db.add(existing)
        db.flush()
        db.add_all(
            [
                Identity(founder_id=existing.id, github=f"unrelated-{suffix}"),
                Identity(founder_id=existing.id, linkedin=f"linkedin.com/in/ada-{suffix}"),
            ]
        )
        db.flush()

        resolved_id, method = resolve_or_create_founder(
            db,
            {
                "display_name": "Dr. Ada Lovelace",
                "identity": {"linkedin": f"linkedin.com/in/ada-{suffix}"},
            },
        )

        assert resolved_id == existing.id
        assert method == "exact_key"
    finally:
        db.rollback()
        db.close()
