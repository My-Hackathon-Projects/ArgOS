"""Database regressions for outbound signal attribution."""

import uuid

from helpers import unique_suffix
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Founder, Identity, Signal, founder_signal
from app.sourcing.persist import persist_delivery


def _founder(name: str, signals: list[dict]) -> dict:
    return {
        "display_name": name,
        "status": "candidate",
        "discovery_confidence": 0.5,
        "signals": signals,
    }


def _signal(suffix: str) -> dict:
    url = f"https://example.test/team-win/{suffix}"
    return {
        "source": "web",
        "signal_type": "hackathon_result",
        "canonical_url": url,
        "content_hash": f"hash-{suffix}",
        "url": url,
        "title": "Team won the hackathon",
        "summary": "The team members won.",
        "source_reliability": 0.7,
        "resolution_confidence": 0.9,
        "resolution_method": "exact_key",
        "sources_seen": ["web"],
    }


def test_shared_artifact_is_attributed_to_every_founder() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        artifact = _signal(suffix)
        result = persist_delivery(
            db,
            [
                _founder(f"Ada {suffix}", [artifact]),
                _founder(f"Grace {suffix}", [artifact]),
            ],
            commit=False,
        )

        founders = (
            db.execute(
                select(Founder).where(
                    Founder.display_name.in_([f"Ada {suffix}", f"Grace {suffix}"])
                )
            )
            .scalars()
            .all()
        )
        signal = db.execute(
            select(Signal).where(Signal.canonical_url == artifact["canonical_url"])
        ).scalar_one()

        assert result["new_founders"] == 2
        assert result["new_signals"] == 1
        assert len(founders) == 2
        assert (
            db.scalar(select(func.count()).select_from(Signal).where(Signal.id == signal.id)) == 1
        )
        attributions = db.execute(
            select(
                founder_signal.c.founder_id,
                founder_signal.c.attribution_confidence,
                founder_signal.c.attribution_method,
            ).where(founder_signal.c.signal_id == signal.id)
        ).all()
        assert len(attributions) == 2
        assert {(confidence, method) for _, confidence, method in attributions} == {
            (0.9, "exact_key")
        }
        assert all(signal.id in {item.id for item in founder.signals} for founder in founders)
    finally:
        db.rollback()
        db.close()


def test_outbound_does_not_create_a_founder_without_an_artifact() -> None:
    db = SessionLocal()
    try:
        name = f"No Evidence {uuid.uuid4().hex}"
        result = persist_delivery(db, [_founder(name, [])], commit=False)

        assert result["new_founders"] == 0
        assert db.scalar(select(Founder.id).where(Founder.display_name == name)) is None
    finally:
        db.rollback()
        db.close()


def test_outbound_resolves_identity_and_shares_one_artifact_between_founders() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        # A spelling variant, not a different human: the name gate (MERGE_NAME_MIN) is the
        # first-order check, so a shared personal handle resolves identity *within* a name that
        # still matches. Two unrelated names sharing a handle is an org account, not a person.
        existing = Founder(display_name=f"Existing {suffix} Persson")
        db.add(existing)
        db.flush()
        db.add(Identity(founder_id=existing.id, github=f"existing-{suffix}"))
        artifact = _signal(suffix)
        resolved = _founder(f"Existing {suffix} Person", [artifact])
        resolved["identity"] = {"github": f"existing-{suffix}"}

        result = persist_delivery(
            db,
            [resolved, _founder(f"New teammate {suffix}", [artifact])],
            commit=False,
        )

        assert result["resolved_to_existing"] == 1
        assert result["new_founders"] == 1
        assert result["new_signals"] == 1
        signal = db.scalar(select(Signal).where(Signal.canonical_url == artifact["canonical_url"]))
        assert signal is not None
        assert (
            db.scalar(
                select(func.count())
                .select_from(founder_signal)
                .where(founder_signal.c.signal_id == signal.id)
            )
            == 2
        )
        assert signal.id in {item.id for item in existing.signals}
    finally:
        db.rollback()
        db.close()


def test_a_new_founder_stores_the_resolved_place_id() -> None:
    """Discovery must persist the canonical place id, not just the derived name/key.

    Regression: _new_founder wrote city/city_key/country_code/location_quality but dropped
    geonameid, so every founder created by discovery carried a resolved-looking location with
    no place identity — exactly the string-matching the id exists to replace. reconcile filled
    it in later, which hid the gap until a real intake run.
    """
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        result = persist_delivery(
            db,
            [
                {
                    "display_name": f"Ada Place {suffix}",
                    "city": "München",
                    "status": "candidate",
                    "discovery_confidence": 0.6,
                    "signals": [_signal(suffix)],
                }
            ],
        )
        assert result["new_founders"] == 1
        founder = db.execute(
            select(Founder).where(Founder.display_name == f"Ada Place {suffix}")
        ).scalar_one()
        assert founder.city == "Munich"
        assert founder.country_code == "DE"
        assert founder.city_geonameid == 2867714
    finally:
        db.close()
