"""Deterministic, explainable normalization for source locations."""

import re
import unicodedata
from dataclasses import dataclass
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
_CITY_CACHE = geonamescache.GeonamesCache(min_city_population=500)
_CITY_ROWS = tuple(cast(dict[str, Any], row) for row in _CITY_CACHE.get_cities().values())
_CITY_BY_KEY: dict[str, list[dict[str, Any]]] = {}
for _row in _CITY_ROWS:
    _CITY_BY_KEY.setdefault(_city_key(str(_row["name"])), []).append(_row)
_COUNTRIES.update(
    {
        _fold(row["name"]): code
        for code, row in _CITY_CACHE.get_countries().items()
        if row.get("name")
    }
)


def _geo_city(head: str, country_code: str | None) -> str | None:
    key = _city_key(head)
    if not key:
        return None
    if key in _ALIASES:
        return _ALIASES[key]
    matches = [
        row
        for row in _CITY_BY_KEY.get(key, ())
        if country_code is None or row.get("countrycode") == country_code
    ]
    if len(matches) == 1:
        return head
    if country_code and matches:
        # Some countries contain multiple small places with the same name. Prefer the largest
        # GeoNames locality while retaining the source spelling for display.
        return max(matches, key=lambda row: row.get("population", 0))["name"]
    return None


def normalize_location(raw: str | None) -> NormalizedLocation:
    """Normalize free text without turning institutions into cities."""
    if raw is None or not raw.strip():
        return NormalizedLocation(raw, None, None, None, "unknown")
    original = raw.strip()
    parts = [part.strip() for part in original.split(",") if part.strip()]
    head = parts[0] if parts else original
    country_code = None
    for part in reversed(parts[1:] or parts):
        country_code = _COUNTRIES.get(_fold(part))
        if country_code:
            break
    head_key = _fold(head)
    if head_key in _NON_CITY:
        return NormalizedLocation(original, None, None, country_code, "unknown")
    if head_key in _COUNTRIES:
        return NormalizedLocation(original, None, None, country_code, "country_only")
    city = _geo_city(head, country_code)
    if city is None:
        # Preserve plausible localities for audit/search even when the local catalogue does not
        # contain them. Short all-caps institution tokens are intentionally not treated as cities.
        if _fold(head) in _NON_CITY or "/" in head or not any(char.isalpha() for char in head):
            return NormalizedLocation(original, None, None, country_code, "unknown")
        return NormalizedLocation(original, head, _city_key(head), country_code, "unknown")
    quality = "exact" if _city_key(city) == _city_key(head) else "inferred"
    return NormalizedLocation(original, city, _city_key(city), country_code, quality)


def normalize_city(raw: str | None) -> str | None:
    """Backward-compatible city-only accessor used by existing sourcing code."""
    return normalize_location(raw).city
