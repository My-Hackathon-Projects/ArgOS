"""normalize_city — collapse free-text location noise into one bucket per city."""

import pytest

from app.normalize import normalize_city, normalize_location, place_key


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
    # Canonical, not the source spelling: "Zurich" resolves to the place whose GeoNames name is
    # "Zürich", which is what puts both spellings in one record.
    assert normalize_city("Zurich") == "Zürich"
    assert normalize_location("Zurich").geonameid == normalize_location("Zürich").geonameid


def test_institution_is_not_silently_converted_to_city():
    location = normalize_location("TUM")
    assert location.city is None
    assert location.quality == "unknown"


def test_every_spelling_resolves_to_one_place_id():
    """The point of the pipeline: variants are one place record, not similar strings.

    Display name, bucket key and canonical id must all agree, so downstream can compare on the
    id rather than hoping two spellings render identically.
    """
    variants = [
        "Munich",
        "München",
        "Muenchen",
        "MUENCHEN",
        "  münchen ",
        "Munich, Germany",
        "München, Bayern, Germany",
    ]
    resolved = [normalize_location(v) for v in variants]
    assert len({r.geonameid for r in resolved}) == 1, [
        (v, r.geonameid) for v, r in zip(variants, resolved, strict=True)
    ]
    assert len({r.city for r in resolved}) == 1
    assert len({r.city_key for r in resolved}) == 1
    assert resolved[0].geonameid == 2867714  # GeoNames id for Munich


def test_diacritic_variants_share_the_display_name_not_just_the_key():
    """Regression: city_key collapsed but `city` kept the source spelling.

    entity_resolution compared the *display* name, so "Zürich" and "Zurich" — same key, same
    place — did not match each other.
    """
    for a, b in [("Zürich", "Zurich"), ("Nürnberg", "Nurnberg"), ("Düsseldorf", "Dusseldorf")]:
        left, right = normalize_location(a), normalize_location(b)
        assert left.city == right.city, f"{a} vs {b} render differently"
        assert left.geonameid == right.geonameid


def test_country_is_populated_from_the_resolved_place():
    """A bare city name still yields a country — the sources rarely state one."""
    assert normalize_location("Munich").country_code == "DE"
    assert normalize_location("Zurich").country_code == "CH"
    assert normalize_location("Tübingen").country_code == "DE"
    assert normalize_location("Seattle").country_code == "US"


def test_endonyms_resolve_through_the_gazetteer_alias_cluster():
    """Exonym/endonym pairs come from GeoNames alternatenames, not a hand-kept list."""
    for endonym, expected in [("Wien", "Vienna"), ("Praha", "Prague"), ("Lisboa", "Lisbon")]:
        assert normalize_location(endonym).city == expected


def test_ambiguous_city_resolves_to_the_dominant_place_and_says_so():
    """ "Berlin" alone used to be quality=unknown while "Springfield, USA" was exact."""
    berlin = normalize_location("Berlin")
    assert berlin.country_code == "DE"
    assert berlin.quality == "inferred"


def test_a_population_guess_is_never_labelled_exact():
    springfield = normalize_location("Springfield, USA")
    assert springfield.quality == "inferred"


def test_unresolved_text_is_labelled_unverified_not_unknown():
    """A kept-but-unverified string must be distinguishable from "nothing parseable"."""
    kept = normalize_location("Nowhereville")
    assert kept.city == "Nowhereville" and kept.geonameid is None
    assert kept.quality == "unverified"
    assert normalize_location("TUM").quality == "unknown"


def test_place_key_is_the_identity_equality_should_use():
    """What entity_resolution compares. Display names are for humans, not for matching."""
    assert place_key("Zürich") == place_key("Zurich") == place_key("Zuerich")
    assert place_key("Wien") == place_key("Vienna")
    assert place_key("München") == place_key("Muenchen") == place_key("Munich")
    assert place_key("Munich") != place_key("Berlin")
    # unresolved free text still compares, on the folded name
    assert place_key("Nowhereville") == "nowhereville"
    assert place_key(None) is None


def test_founder_matching_uses_the_place_not_the_spelling():
    """The regression this whole layer exists for, asserted at the matcher."""
    from app.entity_resolution import FounderCandidate, _context_matches

    for a, b in [("Zürich", "Zurich"), ("Nürnberg", "Nurnberg"), ("Wien", "Vienna")]:
        left = FounderCandidate(display_name="Ada Lovelace", city=a)
        right = FounderCandidate(display_name="Ada Lovelace", city=b)
        assert _context_matches(left, right).get("city") is True, f"{a} vs {b}"

    far = _context_matches(
        FounderCandidate(display_name="Ada Lovelace", city="Munich"),
        FounderCandidate(display_name="Ada Lovelace", city="Berlin"),
    )
    assert far.get("city") is False


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
