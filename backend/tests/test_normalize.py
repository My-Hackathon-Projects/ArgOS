"""normalize_city — collapse free-text location noise into one bucket per city."""

import pytest

from app.normalize import normalize_city, normalize_location


@pytest.mark.parametrize(
    "raw,expected",
    [
        # the Munich cluster observed live: spelling, language, suffix, institution
        ("Munich", "Munich"),
        ("München", "Munich"),
        ("Munich, Germany", "Munich"),
        ("TUM", None),
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
    variants = ["Munich", "München", "Munich, Germany", " münchen "]
    assert {normalize_city(v) for v in variants} == {"Munich"}


def test_distinct_cities_stay_distinct():
    assert normalize_city("Berlin") != normalize_city("Munich")
    assert normalize_city("Zurich") == "Zurich"


def test_institution_is_not_silently_converted_to_city():
    location = normalize_location("TUM")
    assert location.city is None
    assert location.quality == "unknown"


def test_known_us_and_european_cities_have_stable_keys():
    expected = {
        "Tübingen, Germany": ("Tübingen", "tubingen"),
        "Göttingen, Germany": ("Göttingen", "gottingen"),
        "München, Germany": ("Munich", "munich"),
        "London, UK": ("London", "london"),
        "Cambridge, UK": ("Cambridge", "cambridge"),
        "Birmingham, UK": ("Birmingham", "birmingham"),
        "San Francisco, US": ("San Francisco", "san francisco"),
        "Karlsruhe, Germany": ("Karlsruhe", "karlsruhe"),
        "Hamburg, Germany": ("Hamburg", "hamburg"),
        "Berlin, Germany": ("Berlin", "berlin"),
        "Paris, France": ("Paris", "paris"),
    }
    for raw, pair in expected.items():
        location = normalize_location(raw)
        assert (location.city, location.city_key) == pair
