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
    # GeoNames id of the resolved place — the canonical identifier. Two records referring to the
    # same place share this even when the source strings differ, so callers compare places
    # rather than hoping two spellings render identically. None => unresolved free text.
    geonameid: int | None = None


# quality vocabulary, most to least trustworthy:
#   exact       the folded name matched exactly one place (optionally within a known country)
#   alias       resolved through the gazetteer's alternatenames (endonym/exonym) or a
#               transliterated spelling — a real place, reached by a different name
#   inferred    several places share the name; the dominant one by population was chosen
#   unverified  not in the gazetteer; the source string is kept as-is for audit/search
#   country_only  a country with no city component
#   unknown     nothing usable (institution token, placeholder, empty)


def _fold(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold().strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _city_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _fold(value)).strip()


# Hot-path aliases: folded variant -> folded PRIMARY index key. These are the spellings that
# dominate our sources; resolving them here avoids building the 5s gazetteer alias index for the
# most common lookups. The alias index is still the general answer for everything else.
_ALIASES = {
    "munchen": "munich",
    "muenchen": "munich",
    "tuebingen": "tubingen",
    "goettingen": "gottingen",
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
    """Primary index: folded official name -> place rows. ~1s over 223k cities."""
    index: dict[str, list[dict[str, Any]]] = {}
    for row in _geonames().get_cities().values():
        row = cast(dict[str, Any], row)
        index.setdefault(_city_key(str(row["name"])), []).append(row)
    return {key: tuple(rows) for key, rows in index.items()}


# An alternatename is only trustworthy as an identity key when it names exactly one place.
# GeoNames ships plenty that do not: "MUC" (airport code), "Minga"/"Minca" for Munich. Keys
# shorter than this are dropped outright, and any key claimed by two places is discarded — so
# the alias layer cannot invent a merge, only resolve an unambiguous endonym/exonym.
_MIN_ALIAS_KEY_LEN = 4


@cache
def _alias_index() -> dict[str, dict[str, Any]]:
    """Endonym/exonym -> the single place that owns it (Wien->Vienna, Praha->Prague).

    ~5s and ~15MB, so it is built only after the primary index misses. The common path
    (an official name, or one of _ALIASES) never pays for it.
    """
    owners: dict[str, set[int]] = {}
    for row in _geonames().get_cities().values():
        for alt in cast(dict[str, Any], row).get("alternatenames") or []:
            key = _city_key(str(alt))
            if len(key) >= _MIN_ALIAS_KEY_LEN:
                owners.setdefault(key, set()).add(int(row["geonameid"]))
    primary = _city_index()
    by_id = {
        int(row["geonameid"]): cast(dict[str, Any], row)
        for row in _geonames().get_cities().values()
    }
    return {
        key: by_id[next(iter(ids))]
        for key, ids in owners.items()
        if len(ids) == 1 and key not in primary
    }


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


def _dominant(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return max(rows, key=lambda row: row.get("population", 0))


def _resolve_place(head: str, country_hint: str | None) -> tuple[dict[str, Any] | None, str]:
    """Free text -> (gazetteer place row, quality). The candidate-generation cascade.

    Order is exact official name, then the gazetteer's alias cluster, then a transliterated
    spelling. Each step is deterministic and each records *how* it matched, so a population
    tie-break is never reported as an exact hit.
    """
    key = _city_key(head)
    if not key:
        return None, "unknown"
    key = _ALIASES.get(key, key)

    rows = _matching(key, country_hint)
    if rows:
        return (rows[0], "exact") if len(rows) == 1 else (_dominant(rows), "inferred")
    if _city_index().get(key):
        # The name exists but not in the stated country ("Paris, Germany"). Contradictory
        # input — refuse rather than silently relocating the person.
        return None, "unverified"

    def _accept(row: dict[str, Any] | None) -> tuple[dict[str, Any] | None, str]:
        if row is None or (country_hint and row.get("countrycode") != country_hint):
            return None, "unverified"
        return row, "alias"

    alias = _alias_index().get(key)
    if alias is not None:
        return _accept(alias)

    alt = _detransliterate(key)
    if alt != key:
        alt = _ALIASES.get(alt, alt)
        rows = _matching(alt, country_hint)
        if rows:
            return (rows[0] if len(rows) == 1 else _dominant(rows)), "alias"
        return _accept(_alias_index().get(alt))
    return None, "unverified"


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

    is_country = head_key in countries
    if is_country:
        # A city-state's name is both a country and a real city ("Singapore", "Luxembourg",
        # "Monaco"). Matching countries first erased the city outright, so ask the gazetteer
        # before settling for country_only.
        country_code = country_code or countries[head_key]

    place, quality = _resolve_place(head, country_code)
    if place is not None:
        # Canonical storage: the place's own name and id, never the source spelling. This is
        # what makes "Zürich"/"Zurich"/"Zuerich" one record instead of three similar strings.
        name = str(place["name"])
        return NormalizedLocation(
            original,
            name,
            _city_key(name),
            str(place.get("countrycode") or "") or country_code,
            quality,
            int(place["geonameid"]),
        )

    if is_country:
        return NormalizedLocation(original, None, None, country_code, "country_only")
    # Preserve plausible localities for audit/search even when the gazetteer does not contain
    # them. Institution tokens are already filtered by the _NON_CITY check above.
    if "/" in head or not any(char.isalpha() for char in head):
        return NormalizedLocation(original, None, None, country_code, "unknown")
    return NormalizedLocation(original, head, _city_key(head), country_code, "unverified")


def normalize_city(raw: str | None) -> str | None:
    """Canonical display name for a location. For *comparing* places, use `place_key`."""
    return normalize_location(raw).city


def place_key(raw: str | None) -> str | None:
    """Spelling-independent identity for a location — what equality should be tested on.

    The resolved GeoNames id when we have one, else the folded name so unresolved free text
    still compares sensibly. Comparing display names instead (the old behaviour) meant
    "Zürich" and "Zurich" — one place, one id — did not match.
    """
    location = normalize_location(raw)
    if location.geonameid is not None:
        return f"geonames:{location.geonameid}"
    return location.city_key
