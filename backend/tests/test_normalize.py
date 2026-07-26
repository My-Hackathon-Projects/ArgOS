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


def test_city_states_are_not_erased_by_the_country_lookup():
    """A city-state's name is both a country and a real city — it must stay a city.

    The head was matched against the country table *before* the city index, so "Singapore",
    "Luxembourg", "Monaco" and "Djibouti" all resolved to country_only with city=None. Those
    are places founders actually live, and the city was silently dropped.
    """
    for raw, expected_cc in [
        ("Singapore", "SG"),
        ("Singapore, Singapore", "SG"),
        ("Luxembourg", "LU"),
        ("Monaco", "MC"),
    ]:
        location = normalize_location(raw)
        assert location.city is not None, f"{raw} lost its city"
        assert location.country_code == expected_cc
        assert location.quality != "country_only"


def test_a_real_country_is_still_not_a_city():
    """The city-state fix must not turn every country name into a city."""
    for raw in ["Germany", "France", "Deutschland", "United Kingdom"]:
        location = normalize_location(raw)
        assert location.city is None, f"{raw} became a city"
        assert location.quality == "country_only"


def test_german_transliteration_collapses_with_the_umlaut_spelling():
    """ue/oe/ae spellings must land in the same bucket as the umlaut ones.

    entity_resolution compares founders on normalize_city, so "Muenchen" and "München"
    landing in different buckets silently weakens founder dedup.
    """
    assert normalize_city("Muenchen") == normalize_city("München") == "Munich"
    assert normalize_city("Zuerich") == normalize_city("Zürich")
    assert normalize_city("Duesseldorf") == normalize_city("Düsseldorf")
    assert normalize_city("Koeln") == normalize_city("Köln")


def test_transliteration_fallback_does_not_invent_matches():
    """The de-transliterated form is only consulted when the direct key misses."""
    # 'ue' inside a name that is already a real city must not be rewritten
    assert normalize_city("Buenos Aires, Argentina") == "Buenos Aires"
    assert normalize_city("Puebla, Mexico") == "Puebla"


def test_geonames_index_is_not_built_at_import():
    """Import must stay cheap: the ~2.5s GeoNames load is paid on first use, not on import.

    Every CLI entry point, test session and API boot imports this module; most never
    normalize a location.
    """
    import subprocess
    import sys

    probe = (
        "import app.normalize as n; "
        "print(n._city_index.cache_info().currsize, n._country_codes.cache_info().currsize)"
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, check=True
    ).stdout.split()
    assert out == ["0", "0"], f"index built during import: {out}"


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
