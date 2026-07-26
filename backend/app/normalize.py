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


# `quality` records HOW the place was matched — its provenance, not how much to trust the row.
# Read that way, "Zurich -> exact" and "Zuerich -> alias" are both correct: same place, different
# routes to it. What the vocabulary must never do is report a guess as a match.
#
#   exact       the source's own spelling is the place's official name (optionally within a
#               known country)
#   alias       reached by a different name — the gazetteer's alternatenames (Wien -> Vienna), a
#               hot-path alias, or a transliterated spelling (Zuerich -> Zurich)
#   inferred    several places share the name; the dominant one by population was chosen
#   prior       population could not separate real namesakes and the stated Europe-first prior
#               broke the tie. A guess, held to a threshold, and labelled as one.
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

# How much larger the leading candidate must be before population alone decides a namesake.
# Measured over real inputs: the places a writer obviously means dominate by a wide margin
# (New York 904x, Berlin 196x, Roma 64x, Paris 30x, Dublin 18x, Boston 16x), while genuinely
# ambiguous namesakes sit near parity (Stanford 2.1x, Springfield 1.1x, Cambridge 1.1x). Below
# this the name is left unresolved rather than guessed — "Stanford" resolved to Stanford-le-Hope
# in Essex on a 2.1x edge, silently relocating the person.
_DOMINANT_POPULATION_RATIO = 10

# Explicit, stated domain prior — NOT a hidden bias. The thesis sources founders in Europe, so
# when two real namesakes are too close in size to separate, a European one is preferred over a
# non-European one: "Heidelberg" is Baden-Württemberg (143k) not Gauteng (86k, 1.7x), "Valencia"
# is Spain not Venezuela (which is 2x larger), "Cambridge" is England not Ontario. It only ever
# breaks a tie the population rule already declined to call, and never overrides a stated
# country. EU/EEA/UK/CH + Western Balkans; empty this set to disable the prior entirely.
_EUROPE = frozenset(
    """AL AD AT BA BE BG BY CH CY CZ DE DK EE ES FI FR GB GR HR HU IE IS IT LI LT LU LV MC MD
    ME MK MT NL NO PL PT RO RS SE SI SK SM UA VA XK""".split()
)

# How large the European candidate must be relative to the LARGEST candidate before the prior may
# pick it. Without this the prior fired on any namesake, however small, and moved people the wrong
# way across the Atlantic: "Portland, Oregon" and "Springfield" both landed in Britain and were
# reported `exact`. Bounding the top-2 population *ratio* instead does not work — Springfield
# (1.10), Cambridge (1.12) and Princeton (1.33) all sit inside any usable band. Measured against
# the leader the two populations separate cleanly, by 25x:
#
#     portland     US   652,503   best European GB      12,710 =   1.9%   reject
#     springfield  US   170,188                 GB         960 =   0.6%   reject (a village)
#     princeton    US    39,308   no European candidate                   reject
#     stanford     US    13,809   no European candidate                   reject
#     valencia     VE 1,619,470   best European ES     825,948 =  51.0%   keep  <- binding case
#     cambridge    GB   145,674                 GB     145,674 = 100.0%   keep
#     heidelberg   DE   143,345                 DE     143,345 = 100.0%   keep
#
# Every approved case is 51-100%, every misfire 0.6-1.9%. Same evidentiary style as MERGE_NAME_MIN.
_EUROPE_MIN_SHARE = 0.5


@cache
def _by_geonameid() -> dict[int, dict[str, Any]]:
    return {
        int(row["geonameid"]): cast(dict[str, Any], row)
        for row in _geonames().get_cities().values()
    }


@cache
def _alias_index() -> dict[str, tuple[int, ...]]:
    """Endonym/exonym -> the place ids that claim it (Wien->Vienna, Praha->Prague).

    Ids rather than rows to keep this cheap; ~5s to build, so it is only consulted after the
    primary index fails. The common path (an official name, or one of _ALIASES) never pays it.

    Ambiguous keys are kept, not dropped: "muenster" is claimed by both Münster (DE) and
    Muenster (TX), and a stated country is exactly what tells them apart. `_from_alias` accepts
    a multi-owner key only when context narrows it to one, so the layer still cannot guess.
    """
    # Lists, not sets: the overwhelming majority of alias keys name exactly one place, so the
    # per-key set allocation dominated the build. Duplicates are collapsed only where they occur.
    owners: dict[str, list[int]] = {}
    for row in _geonames().get_cities().values():
        gid = int(row["geonameid"])
        for alt in cast(dict[str, Any], row).get("alternatenames") or []:
            key = _city_key(str(alt))
            if len(key) >= _MIN_ALIAS_KEY_LEN:
                owners.setdefault(key, []).append(gid)
    return {
        key: (tuple(ids) if len(ids) == 1 else tuple(dict.fromkeys(ids)))
        for key, ids in owners.items()
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


def _population(row: dict[str, Any]) -> int:
    return int(row.get("population", 0) or 0)


def _dominant(rows: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    return max(rows, key=_population)


def _decisive(
    rows: list[dict[str, Any]], *, prefer_europe: bool = False
) -> tuple[dict[str, Any] | None, str]:
    """The clear winner and HOW it won, or (None, "none") when the field is too close to call.

    Guessing between real namesakes of comparable size relocates people: "Stanford" resolved to
    Stanford-le-Hope in Essex on a 2.1x edge. The caller needs the reason, not just the row —
    a place the Europe prior guessed at must not be recorded with the same quality as one whose
    official name the source actually wrote.
    """
    if not rows:
        return None, "none"
    if len(rows) == 1:
        return rows[0], "sole"
    ranked = sorted(rows, key=_population, reverse=True)
    if _population(ranked[0]) >= _DOMINANT_POPULATION_RATIO * max(_population(ranked[1]), 1):
        return ranked[0], "population"
    # Too close on size alone. Fall back to the stated Europe-first prior, and only if it
    # actually narrows the field — a tie between two European places is still a tie.
    # Applied to official-name candidates only: over the alias-inflated pool it let
    # Stanford-le-Hope (Essex) outrank the exact-name match Stanford, US.
    if not prefer_europe:
        return None, "none"
    european = [row for row in ranked if row.get("countrycode") in _EUROPE]
    if not european or len(european) == len(ranked):
        return None, "none"
    # The prior breaks ties between comparable namesakes; it does not relocate a person to a
    # village because the village is European. See _EUROPE_MIN_SHARE.
    if _population(european[0]) < _EUROPE_MIN_SHARE * _population(ranked[0]):
        return None, "none"
    if len(european) == 1:
        return european[0], "prior"
    if _population(european[0]) >= _DOMINANT_POPULATION_RATIO * max(_population(european[1]), 1):
        return european[0], "prior"
    return None, "none"


def _resolve_place(head: str, country_hint: str | None) -> tuple[dict[str, Any] | None, str]:
    """Free text -> (gazetteer place row, quality). The candidate-generation cascade.

    Order is exact official name, then the gazetteer's alias cluster, then a transliterated
    spelling. Each step is deterministic and each records *how* it matched, so a population
    tie-break is never reported as an exact hit.
    """
    original_key = _city_key(head)
    if not original_key:
        return None, "unknown"
    key = _ALIASES.get(original_key, original_key)

    def _alias_rows(alias_key: str) -> tuple[dict[str, Any], ...]:
        ids = _alias_index().get(alias_key) or ()
        rows = tuple(_by_geonameid()[i] for i in ids)
        if country_hint:
            rows = tuple(r for r in rows if r.get("countrycode") == country_hint)
        return rows

    def _decide(alias_key: str) -> tuple[dict[str, Any] | None, str]:
        """Pool official names and the gazetteer's alias cluster, then choose.

        Consulting official names *first* let a namesake win outright: "Roma" is a 25k town in
        Lesotho and the endonym for Rome (2.8M), and the Lesotho row was returned. Pooling both
        candidate sets and taking the dominant place fixes that, and also resolves cities whose
        official name nobody writes ("New York" -> "New York City").

        A country hint has already filtered both sets, so an explicit country still beats
        population.
        """
        primary = _matching(alias_key, country_hint)
        pool: dict[int, dict[str, Any]] = {int(r["geonameid"]): r for r in primary}
        pool.update({int(r["geonameid"]): r for r in _alias_rows(alias_key)})
        if not pool:
            # The name is known, just not in the country the source stated ("Paris, Germany").
            # Distinguished from "never heard of it" so the caller can drop the bogus country
            # instead of recording the person in a Paris that does not exist.
            known_elsewhere = bool(_city_index().get(alias_key) or _alias_index().get(alias_key))
            return None, "contradicted" if (country_hint and known_elsewhere) else "unverified"
        # An official name is stronger evidence than an alternatename, which is why the two are
        # weighed apart: GeoNames lists "Rome" as an alternatename of Lomé (2.19M), which nearly
        # ties Rome (2.32M) and would block the decision if pooled naively.
        named = [r for r in pool.values() if _city_key(str(r["name"])) == alias_key]
        best_named, named_how = _decisive(named, prefer_europe=True)
        best_pool, pool_how = _decisive(list(pool.values()))
        # An alias candidate only overrules an exact name match by dominating it outright —
        # "Roma" is a 14k town in Lesotho and the endonym of Rome, 163x larger.
        if (
            best_pool is not None
            and best_named is not None
            and _population(best_pool)
            >= _DOMINANT_POPULATION_RATIO * max(_population(best_named), 1)
        ):
            return best_pool, "inferred"
        if best_named is not None:
            if named_how == "prior":
                return best_named, "prior"
            # `alias_key` is the key that actually matched. When it is not the source's own
            # folded spelling, the place was reached under a different name — a hot-path alias
            # or a transliteration — and saying `exact` would claim the source wrote this name.
            return best_named, "exact" if alias_key == original_key else "alias"
        if best_pool is not None:
            # Nothing carries this as an official name, so it was reached through the gazetteer's
            # alternatenames. One owner is an unambiguous endonym/exonym (Wien -> Vienna);
            # several means population picked among namesakes.
            return best_pool, "alias" if pool_how == "sole" else "inferred"
        # Real namesakes of comparable size. Guessing relocates people; leave it to a country
        # hint or a human.
        return None, "unverified"

    place, quality = _decide(key)
    if place is not None:
        return place, quality
    unresolved = quality  # "contradicted" or "unverified" — must survive the fallthrough

    alt = _detransliterate(key)
    if alt != key:
        place, quality = _decide(_ALIASES.get(alt, alt))
        if place is not None:
            return place, quality
        if quality == "contradicted":
            unresolved = quality
    # Either nothing names this place, or the name exists only in a country the source
    # contradicts ("Paris, Germany"). Keep the raw string rather than relocating the person.
    return None, unresolved


def normalize_location(raw: str | None, *, country_hint: str | None = None) -> NormalizedLocation:
    """Normalize free text without turning institutions into cities.

    `country_hint` is context the *caller* knows and the string does not — in practice the country
    of the founder's institution (`app.places`). It narrows the candidate pool before either
    heuristic runs, which is what turns "Cambridge" from a coin-flip into a fact. It is evidence,
    not an assertion: a country stated in the string always wins, and a hint that finds nothing is
    dropped and the lookup retried without it, rather than leaving the person unplaced.
    """
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
        # The hint only ever narrows gazetteer candidates. It never becomes stored data on its
        # own, or "unknown" would start asserting a country nothing resolved.
        return NormalizedLocation(original, None, None, country_code, "unknown")

    is_country = head_key in countries
    if is_country:
        # A city-state's name is both a country and a real city ("Singapore", "Luxembourg",
        # "Monaco"). Matching countries first erased the city outright, so ask the gazetteer
        # before settling for country_only.
        country_code = country_code or countries[head_key]

    stated_country = country_code
    place, quality = _resolve_place(head, country_code or country_hint)
    if quality == "contradicted" and stated_country is None and country_hint is not None:
        # The hint was wrong about this person, not about the world — they moved, or the string
        # names somewhere they never studied. Retry unhinted rather than record nothing. Only on
        # `contradicted`, which means the hinted country has no such place at all: when it has
        # several and none is decisive, dropping the hint would trade a hard "we cannot tell"
        # for a confident answer in the wrong country ("Cambridge" + US -> Cambridge, England).
        place, quality = _resolve_place(head, None)
    if place is None and quality == "contradicted":
        # The city and the country disagree. Keeping the stated country would assert a place
        # that does not exist; the full original string survives in raw_location either way.
        country_code = None
        quality = "unverified"
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

    if is_country and country_code:
        return NormalizedLocation(original, None, None, country_code, "country_only")
    # `country_only` names a country and nothing else, so a NULL country_code makes it a label
    # with no content — and one that reads as *more* resolved than `unknown` while carrying
    # strictly less. Reachable when the string contradicted itself ("Paris, Germany") and the
    # bogus country was dropped above.
    if is_country:
        return NormalizedLocation(original, None, None, None, "unknown")
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
