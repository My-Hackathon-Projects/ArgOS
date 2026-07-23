"""normalize_city — collapse free-text location noise into one bucket per city."""

import pytest

from app.normalize import normalize_city


@pytest.mark.parametrize(
    "raw,expected",
    [
        # the Munich cluster observed live: spelling, language, suffix, institution
        ("Munich", "Munich"),
        ("München", "Munich"),
        ("Munich, Germany", "Munich"),
        ("TUM", "Munich"),
        ("  münchen ", "Munich"),
        # suffix stripping keeps the real, distinct city
        ("Tübingen", "Tübingen"),
        ("Tübingen, Baden-Württemberg, Germany", "Tübingen"),
        ("Garching, Bavaria, Germany", "Garching"),
        ("Lima, Peru", "Lima"),
        ("Lisbon, Portugal", "Lisbon"),
        # country-only / placeholder / empty -> not a city
        ("Germany", None),
        ("null", None),
        ("", None),
        ("   ", None),
        (None, None),
    ],
)
def test_normalize_city(raw, expected):
    assert normalize_city(raw) == expected


def test_munich_variants_collapse_to_one_bucket():
    variants = ["Munich", "München", "Munich, Germany", "TUM", " münchen "]
    assert {normalize_city(v) for v in variants} == {"Munich"}


def test_distinct_cities_stay_distinct():
    assert normalize_city("Berlin") != normalize_city("Munich")
    assert normalize_city("Zurich") == "Zurich"
