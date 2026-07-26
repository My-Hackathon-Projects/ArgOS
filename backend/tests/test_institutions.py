"""Institution resolution — one university, one ROR id.

The suite never touches the network: `lookup_ror` is stubbed at the module seam. The single test
that does hit ROR is marked `live_ror` and deselected by default, so CI stays hermetic while the
real contract can still be checked on demand:

    uv run pytest -m live_ror
"""

from typing import cast

import httpx
import pytest
from sqlalchemy import func, select

from app import institutions as institutions_mod
from app.db import SessionLocal
from app.institutions import institution_key, resolve_institution
from app.models import Institution, InstitutionAlias

TUM = {
    "ror_id": "02kkvpp62",
    "name": "Technical University of Munich",
    "country_code": "DE",
    "score": 1.0,
}


def test_institution_key_collapses_the_spellings_of_one_university():
    """The cache key stops the same string being sent twice; ROR decides identity."""
    assert institution_key("Technical University of Munich") == institution_key(
        "Technical University of Munich (TUM)"
    )
    assert institution_key("technical university of munich  ") == institution_key(
        "The Technical University of Munich"
    )
    # Diacritics fold away...
    assert institution_key("Technische Universität München") == "technische universitat munchen"
    # ...but ue/oe/ae transliteration deliberately does NOT, because rewriting a stored key would
    # mangle real names ("Queen Mary" -> "Qun Mary"). The place layer can afford that rule only
    # because it uses it as a throwaway fallback lookup, never as the key it keeps. Two keys here
    # just mean two ROR calls landing on one ror_id — identity lives there, not in the key.
    assert institution_key("Technische Universitaet Muenchen") != institution_key(
        "Technische Universität München"
    )
    assert institution_key(None) is None
    assert institution_key("  ") is None
    # meaningful differences survive: these are genuinely different organisations
    assert institution_key("Bundeswehr University Munich") != institution_key(
        "Technical University of Munich"
    )


def test_every_spelling_resolves_to_one_institution_row(monkeypatch):
    """The live defect: 71 founders, four strings, no way to join them."""
    calls: list[str] = []

    def fake_lookup(name, *, client=None):
        calls.append(name)
        return dict(TUM)

    monkeypatch.setattr(institutions_mod, "lookup_ror", fake_lookup)
    db = SessionLocal()
    try:
        spellings = [
            "Technical University of Munich",
            "Technische Universität München",
            "Technical University of Munich (TUM)",
            "Technische Universität München (TUM)",
        ]
        resolved = [resolve_institution(db, s) for s in spellings]
        assert all(r is not None for r in resolved)
        assert len({r.id for r in resolved if r}) == 1, "one university, one row"
        assert len({r.ror_id for r in resolved if r}) == 1
        n = db.execute(select(func.count()).select_from(Institution)).scalar_one()
        assert n == 1
        # two distinct cache keys ("(TUM)" is stripped), so ROR was asked twice, not four times
        assert len(calls) == 2, calls
    finally:
        db.rollback()
        db.close()


def test_a_resolved_string_is_never_sent_to_ror_twice(monkeypatch):
    calls: list[str] = []

    def fake_lookup(name, *, client=None):
        calls.append(name)
        return dict(TUM)

    monkeypatch.setattr(institutions_mod, "lookup_ror", fake_lookup)
    db = SessionLocal()
    try:
        for _ in range(3):
            resolve_institution(db, "Technical University of Munich")
        assert len(calls) == 1, calls
    finally:
        db.rollback()
        db.close()


def test_an_unmatched_string_is_negatively_cached_not_retried(monkeypatch):
    """A miss must be recorded, or every run re-queries the same hopeless strings forever."""
    calls: list[str] = []

    def fake_lookup(name, *, client=None):
        calls.append(name)
        return None

    monkeypatch.setattr(institutions_mod, "lookup_ror", fake_lookup)
    db = SessionLocal()
    try:
        assert resolve_institution(db, "Wilhelmsgymnasium München") is None
        assert resolve_institution(db, "Wilhelmsgymnasium München") is None
        assert len(calls) == 1, calls
        alias = db.execute(
            select(InstitutionAlias).where(
                InstitutionAlias.alias_key == institution_key("Wilhelmsgymnasium München")
            )
        ).scalar_one()
        assert alias.institution_id is None
        assert alias.raw_name == "Wilhelmsgymnasium München"
    finally:
        db.rollback()
        db.close()


def test_only_a_chosen_ror_match_is_accepted(monkeypatch):
    """ROR's `chosen` flag is the accept signal — a high score alone is not enough.

    Measured on real strings: "Bundeswehr University Munich" returns "He University" at 0.92 and
    "Wilhelmsgymnasium München" returns "MTU Aero Engines" at 0.9, neither chosen. Applying our
    own score cutoff instead would have accepted both.
    """
    payload = {
        "items": [
            {
                "chosen": False,
                "score": 0.92,
                "organization": {
                    "id": "https://ror.org/00x4qp065",
                    "names": [{"value": "He University", "types": ["ror_display"]}],
                },
            }
        ]
    }

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class FakeClient:
        def get(self, _url, params=None):
            return FakeResponse()

    stub = cast(httpx.Client, FakeClient())
    assert institutions_mod.lookup_ror("Bundeswehr University Munich", client=stub) is None


@pytest.mark.live_ror
def test_ror_contract_against_the_live_api():
    """Opt-in: confirms ROR still answers the way this module assumes."""
    with httpx.Client(timeout=25, follow_redirects=True) as client:
        for spelling in [
            "Technical University of Munich",
            "Technische Universität München",
            "Technical University of Munich (TUM)",
        ]:
            match = institutions_mod.lookup_ror(spelling, client=client)
            assert match is not None, spelling
            assert match["ror_id"] == "02kkvpp62", (spelling, match)
        # an abbreviation alone is not confidently matchable — must not be forced
        assert institutions_mod.lookup_ror("TUM", client=client) is None
