"""A founder's place is written in one place, from the founder's own evidence."""

import uuid

from helpers import unique_suffix
from sqlalchemy import select

from app.db import SessionLocal
from app.institutions import institution_key
from app.models import Founder, Institution, InstitutionAlias
from app.places import apply_location, institution_country
from app.sourcing.persist import persist_delivery


def _affiliated(db, school: str, country: str) -> None:
    """Register `school` as a ROR-resolved institution in `country`."""
    institution = Institution(
        ror_id=f"https://ror.org/{uuid.uuid4().hex[:9]}", name=school, country_code=country
    )
    db.add(institution)
    db.flush()
    db.add(
        InstitutionAlias(
            alias_key=institution_key(school), raw_name=school, institution_id=institution.id
        )
    )
    db.flush()


def test_the_institution_country_decides_a_city_that_population_cannot() -> None:
    """Cambridge is a coin-flip by population; a founder's own affiliation is not."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        school = f"University of Cambridge {suffix}"
        _affiliated(db, school, "GB")
        founder = Founder(
            display_name=f"Ada Lovelace {suffix}",
            education=[{"school": school, "degree": "PhD"}],
        )
        db.add(founder)
        db.flush()

        assert institution_country(db, founder) == "GB"
        location = apply_location(db, founder, "Cambridge")
        assert location.country_code == "GB"
        # Reached under its own official name inside a known country, not guessed by the prior.
        assert location.quality == "exact"
        assert founder.city_geonameid == location.geonameid
    finally:
        db.rollback()
        db.close()


def test_affiliations_in_two_countries_are_not_evidence_of_either() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        british = f"University of Cambridge {suffix}"
        american = f"Massachusetts Institute of Technology {suffix}"
        _affiliated(db, british, "GB")
        _affiliated(db, american, "US")
        founder = Founder(
            display_name=f"Grace Hopper {suffix}",
            education=[{"school": british}, {"school": american}],
        )
        db.add(founder)
        db.flush()

        assert institution_country(db, founder) is None
    finally:
        db.rollback()
        db.close()


def test_a_resolved_place_is_written_whole_or_not_at_all() -> None:
    """Every place column moves together — a lone `city` string compares against nothing.

    `place_key` identifies a location by its geonameid, and `audit_identity` asserts that a
    resolved city carries both its id and its country. Writing `.city` alone (what the enrichment
    path did) produces a founder who fails both while looking placed.
    """
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Alan Turing {suffix}")
        db.add(founder)
        db.flush()

        apply_location(db, founder, "Zuerich")

        assert founder.city == "Zürich"
        assert founder.city_key == "zurich"
        assert founder.city_geonameid is not None
        assert founder.country_code == "CH"
        # Reached by a transliterated spelling, so provenance says `alias`, not `exact`.
        assert founder.location_quality == "alias"
        assert founder.raw_location == "Zuerich"
    finally:
        db.rollback()
        db.close()


def test_re_resolving_never_promotes_a_derived_city_into_raw_location() -> None:
    """`raw_location` is what a source said. `city` is what this module decided it meant."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Katherine Johnson {suffix}")
        db.add(founder)
        db.flush()
        apply_location(db, founder, "muenchen")
        assert founder.raw_location == "muenchen"
        assert founder.city == "Munich"

        apply_location(db, founder)

        assert founder.raw_location == "muenchen", "re-resolution must not overwrite provenance"
        assert founder.city == "Munich"
    finally:
        db.rollback()
        db.close()


def test_enriching_a_known_founder_with_a_city_fills_every_place_column() -> None:
    """The live gap: the enrichment path set `.city` and left the other five NULL."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Barbara Liskov {suffix}"
        artifact = {
            "source": "arxiv",
            "signal_type": "publication",
            "canonical_url": f"https://arxiv.test/abs/{suffix}-1",
            "content_hash": f"hash-{suffix}-1",
            "url": f"https://arxiv.test/abs/{suffix}-1",
            "title": "Paper",
            "summary": "A paper.",
            "source_reliability": 0.8,
            "sources_seen": ["arxiv"],
        }
        persist_delivery(
            db,
            [{"display_name": name, "status": "candidate", "signals": [artifact]}],
            commit=False,
        )
        founder = db.scalar(select(Founder).where(Founder.display_name.contains(suffix)))
        assert founder is not None and founder.city is None

        later = dict(artifact, canonical_url=f"https://arxiv.test/abs/{suffix}-2")
        later["content_hash"] = f"hash-{suffix}-2"
        persist_delivery(
            db,
            [{"display_name": name, "status": "candidate", "city": "Munich", "signals": [later]}],
            commit=False,
        )
        db.expire(founder)

        assert founder.city == "Munich"
        assert founder.city_key == "munich"
        assert founder.city_geonameid is not None
        assert founder.country_code == "DE"
        assert founder.location_quality == "exact"
        assert founder.raw_location == "Munich"
    finally:
        db.rollback()
        db.close()
