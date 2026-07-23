"""Canonicalize free-text founder location into a single city bucket.

Founder.city arrives as free text from discovery ("München", "Munich, Germany",
"TUM", "Germany", "null", ...). Left raw it fragments the city filter into
near-duplicate buckets. This collapses the obvious variants deterministically:
drop a trailing region/country ("X, State, Country" -> "X"), fold known aliases
(München / TUM -> Munich), and drop country-only or placeholder values to None.
No LLM — an explicit, testable map. Extend _ALIAS / _NON_CITY as new noise appears.
"""

import unicodedata


def _fold(s: str) -> str:
    """Accent-fold + lowercase, for case/diacritic-insensitive key matching."""
    decomposed = unicodedata.normalize("NFKD", s.lower().strip())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


# Folded-key -> canonical city. Merges spelling / language / institution variants.
_ALIAS = {
    "munchen": "Munich",
    "munich": "Munich",
    "tum": "Munich",  # Technical University of Munich -> its city
}

# Folded keys that are NOT a city (country-only / placeholder) -> drop to None.
_NON_CITY = {
    "germany",
    "deutschland",
    "usa",
    "united states",
    "null",
    "none",
    "n/a",
    "na",
    "unknown",
    "",
}


def normalize_city(raw: str | None) -> str | None:
    """Free-text location -> canonical city, or None when it isn't a usable city.

    "München" / "Munich, Germany" / "TUM" -> "Munich"; "Germany" / "null" -> None;
    genuine distinct cities pass through with their region/country suffix stripped.
    """
    if raw is None:
        return None
    # Drop a trailing region/country: "Tübingen, Baden-Württemberg, Germany" -> "Tübingen".
    head = raw.split(",")[0].strip()
    if not head:
        return None
    key = _fold(head)
    if key in _NON_CITY:
        return None
    if key in _ALIAS:
        return _ALIAS[key]
    return head
