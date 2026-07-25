"""The founder table holds people. Every rejection here is a real row found in the dev database."""

import pytest
from helpers import unique_suffix
from sqlalchemy import func, select

from app.db import SessionLocal
from app.entity_resolution import is_person_name
from app.models import Founder
from app.sourcing.persist import persist_delivery

# Non-person rows discovery actually created, each carrying signals and a Founder Score.
OBSERVED_NON_PERSONS = [
    "MakeUofT 2026",
    "TUM.ai Makeathon 2024",
    "TreeHacks 2026",
    "hackaTUM 2025",
    "MunichTech EXPO",
    "UAB THE HACK! x Deloitte 2026",
    "RoboHack 2026",
    "Road to START Hack",
    "Hack Roboy",
    "TUM.ai",
    "THUNLP",
    "mit-han-lab",
    "tum-ei-eda",
    "TUM-Dev",
    "microsoft/unilm",
    "annu12340",
    "curatorshashi",
    "Pooya_Sh",
    "valK0WiIn",
    "TekBoArt",
]

# Real founders in the dev database. None of these may ever be rejected.
OBSERVED_PEOPLE = [
    "Mario Krenn",
    "Philipp Hennig",
    "Fabian H. Sinz",
    "Flavio Rump",
    "Taylor T. Johnson",
    "Diego Manzanas Lopez",
    "Ayana A. Wild",
    "Prof. Stefan Feuerriegel",
    "Dr. Ada Lovelace",
    "Alexander H. D. M. Ewering",
    "Sofia Catalina Rodriguez Vidal",
    "Ekaterina Kneschaurek",
    "Stephan Rössler",
    "Carlos Ruiz-Gonzalez",
    "Marius Hobbhahn",
]


@pytest.mark.parametrize("name", OBSERVED_NON_PERSONS)
def test_non_person_names_are_rejected(name: str) -> None:
    assert is_person_name(name) is False


@pytest.mark.parametrize("name", OBSERVED_PEOPLE)
def test_real_founder_names_are_accepted(name: str) -> None:
    assert is_person_name(name) is True


def test_persist_refuses_to_create_a_founder_for_an_event() -> None:
    """The gate lives at the single writer, so no caller can bypass it."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        url = f"https://devpost.test/{suffix}"
        artifact = {
            "source": "web",
            "signal_type": "hackathon",
            "canonical_url": url,
            "content_hash": f"hash-{suffix}",
            "url": url,
            "title": "Event page",
            "source_reliability": 0.6,
        }
        result = persist_delivery(
            db,
            [
                {"display_name": f"RoboHack 2026 {suffix}", "signals": [artifact]},
                {"display_name": f"Ada Lovelace {suffix}", "signals": [artifact]},
            ],
            commit=False,
        )

        assert result["dropped_non_person"] == 1
        assert result["new_founders"] == 1
        names = db.scalars(
            select(Founder.display_name).where(Founder.display_name.contains(suffix))
        ).all()
        assert names == [f"Ada Lovelace {suffix}"]
        assert (
            db.scalar(
                select(func.count())
                .select_from(Founder)
                .where(Founder.display_name.contains("RoboHack"))
            )
            == 0
        )
    finally:
        db.rollback()
        db.close()
