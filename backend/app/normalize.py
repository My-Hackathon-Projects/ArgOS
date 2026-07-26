"""Deterministic, explainable normalization for source locations.

The GeoNames catalogue costs ~2.5s to load and index. It is built lazily on first lookup, not
at import: every CLI entry point, test session and API boot imports this module, and most never
normalize a location. `entity_resolution` compares founders on `normalize_city`, so a name that
lands in the wrong bucket silently weakens founder dedup — the accuracy notes below matter.
"""

import re
import unicodedata
from dataclasses import dataclass
from functools import cache
from typing import Any, cast

import geonamescache


@dataclass(frozen=True)
class NormalizedLocation:
    raw_location: str | None
    city: str | None
    city_key: str | None
    country_code: str | None
    quality: str


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _city_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _fold(value)).strip()


_ALIASES = {
    "munchen": "Munich",
    "munich": "Munich",
    "tubingen": "Tübingen",
    "tuebingen": "Tübingen",
    "gottingen": "Göttingen",
    "goettingen": "Göttingen",
}

_COUNTRIES = {
    "germany": "DE",
    "deutschland": "DE",
    "uk": "GB",
    "united kingdom": "GB",
    "england": "GB",
    "france": "FR",
    "usa": "US",
    "us": "US",
    "united states": "US",
}

_NON_CITY = {"", "null", "none", "n/a", "na", "unknown", "tum", "lmu", "eth", "mit"}


@cache
def _geonames() -> geonamescache.GeonamesCache:
    """Loaded on first lookup. ~2.5s — never paid by a process that only imports this module."""
    return geonamescache.GeonamesCache(min_city_population=500)


@cache
def _city_index() -> dict[str, tuple[dict[str, Any], ...]]:
    index: dict[str, list[dict[str, Any]]] = {}
    for row in _geonames().get_cities().values():
        row = cast(dict[str, Any], row)
        index.setdefault(_city_key(str(row["name"])), []).append(row)
    return {key: tuple(rows) for key, rows in index.items()}


@cache
def _country_codes() -> dict[str, str]:
    codes = dict(_COUNTRIES)
    codes.update(
        {
            _fold(row["name"]): code
            for code, row in _geonames().get_countries().items()
            if row.get("name")
        }
    )
    return codes


def _detransliterate(key: str) -> str:
    """German ue/oe/ae -> u/o/a, so "Muenchen" can reach the "munchen" bucket.

    Only ever used as a *fallback* after the direct key misses, and only accepted if the result
    matches a real city. A nonsense rewrite ("buenos aires" -> "bunos aires") simply finds
    nothing and changes no outcome.
    """
    return key.replace("ue", "u").replace("oe", "o").replace("ae", "a")


def _matching(key: str, country_code: str | None) -> tuple[dict[str, Any], ...]:
    return tuple(
        row
        for row in _city_index().get(key, ())
        if country_code is None or row.get("countrycode") == country_code
    )


def _geo_city(head: str, country_code: str | None) -> str | None:
    key = _city_key(head)
    if not key:
        return None
    if key in _ALIASES:
        return _ALIASES[key]

    matches = _matching(key, country_code)
    if len(matches) == 1:
        return head  # source spelling preserved for display
    if country_code and matches:
        # Some countries contain multiple small places with the same name. Prefer the largest
        # GeoNames locality while retaining the source spelling for display.
        return max(matches, key=lambda row: row.get("population", 0))["name"]
    if matches:
        return None  # ambiguous across countries — refuse to guess

    # Nothing under the folded key. Try the German transliteration before giving up.
    alt = _detransliterate(key)
    if alt == key:
        return None
    if alt in _ALIASES:
        return _ALIASES[alt]
    alt_matches = _matching(alt, country_code)
    if not alt_matches:
        return None
    # Return the CANONICAL name here, not the source spelling: the whole point of resolving
    # "Zuerich" through "zurich" is that it lands in the same bucket as "Zürich".
    return max(alt_matches, key=lambda row: row.get("population", 0))["name"]


def normalize_location(raw: str | None) -> NormalizedLocation:
    """Normalize free text without turning institutions into cities."""
    if raw is None or not raw.strip():
        return NormalizedLocation(raw, None, None, None, "unknown")
    original = raw.strip()
    parts = [part.strip() for part in original.split(",") if part.strip()]
    head = parts[0] if parts else original
    countries = _country_codes()
    country_code = None
    for part in reversed(parts[1:] or parts):
        country_code = countries.get(_fold(part))
        if country_code:
            break
    head_key = _fold(head)
    if head_key in _NON_CITY:
        return NormalizedLocation(original, None, None, country_code, "unknown")

    def _resolved(city: str) -> NormalizedLocation:
        quality = "exact" if _city_key(city) == _city_key(head) else "inferred"
        return NormalizedLocation(original, city, _city_key(city), country_code, quality)

    if head_key in countries:
        # A city-state's name is both a country and a real city ("Singapore", "Luxembourg",
        # "Monaco"). Matching countries first erased the city outright, so ask the catalogue
        # before settling for country_only.
        country_code = country_code or countries[head_key]
        city = _geo_city(head, country_code)
        return (
            _resolved(city)
            if city
            else NormalizedLocation(original, None, None, country_code, "country_only")
        )

    city = _geo_city(head, country_code)
    if city is None:
        # Preserve plausible localities for audit/search even when the local catalogue does not
        # contain them. Short all-caps institution tokens are intentionally not treated as cities
        # (they are already filtered by the _NON_CITY check above).
        if "/" in head or not any(char.isalpha() for char in head):
            return NormalizedLocation(original, None, None, country_code, "unknown")
        return NormalizedLocation(original, head, _city_key(head), country_code, "unknown")
    return _resolved(city)


def normalize_city(raw: str | None) -> str | None:
    """Backward-compatible city-only accessor used by existing sourcing code."""
    return normalize_location(raw).city
