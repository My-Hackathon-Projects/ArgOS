"""Institution resolution — one university, one ROR id.

Affiliations arrive as free text, and the same organisation shows up under many strings. In the
dev DB one university accounted for four of them:

    56  Technical University of Munich
     9  Technische Universität München
     5  Technical University of Munich (TUM)
     1  Technische Universität München (TUM)

Same problem the place layer had, and the same shape of answer: resolve to a registry identifier
and store that, rather than trying to make strings agree. ROR (Research Organization Registry) is
the canonical registry — ~110k organisations, strong European coverage, free, no API key.

Why the `affiliation` endpoint and not `query`: `query` is a relevance search that happily returns
a top hit for anything ("TUM" -> Technical University of Mombasa). `affiliation` is ROR's own
matcher and reports a `chosen` flag alongside a score. Measured against our real strings, every
`chosen` result was correct and every wrong result was NOT chosen ("Bundeswehr University Munich"
-> "He University", 0.92, not chosen). So `chosen` is the accept signal, and anything else is left
unresolved for review rather than guessed.

Every lookup is cached in `institution_alias`, including misses — a string is sent to ROR at most
once, ever. Nothing here runs inside discovery: resolution is an explicit enrichment step
(`app/maintenance/resolve_institutions.py`), so intake never depends on a third-party API.
"""

import re
import unicodedata

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Institution, InstitutionAlias

ROR_AFFILIATION_URL = "https://api.ror.org/v2/organizations"
ROR_TIMEOUT_SECONDS = 20

# Tokens that carry no identity for an organisation name. Deliberately small: over-normalizing
# erases meaningful differences ("Bundeswehr", a campus, a faculty), which is worse than a miss.
_NOISE = frozenset({"the", "of", "at", "de", "der", "des", "und", "and"})


def institution_key(name: str | None) -> str | None:
    """Normalized cache key for an affiliation string.

    Only mechanical normalization — case, accents, punctuation, bracketed extras, filler words.
    It exists to stop the same string being sent to ROR twice, NOT to decide identity; ROR does
    that. "Technical University of Munich" and "Technical University of Munich (TUM)" collapse
    here, while "TU Munich" does not — and does not need to, because both resolve to one ror_id.
    """
    raw = (name or "").strip()
    if not raw:
        return None
    # Drop bracketed abbreviations: "... (TUM)" adds nothing the registry needs.
    raw = re.sub(r"[\(\[][^)\]]*[\)\]]", " ", raw)
    folded = unicodedata.normalize("NFKD", raw.casefold())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    tokens = [t for t in re.findall(r"[a-z0-9]+", folded) if t not in _NOISE]
    return " ".join(tokens) or None


def _ror_display_name(organization: dict) -> str | None:
    names = organization.get("names") or []
    for entry in names:
        if "ror_display" in (entry.get("types") or []):
            return entry.get("value")
    return names[0].get("value") if names else None


def _ror_country(organization: dict) -> str | None:
    for location in organization.get("locations") or []:
        details = location.get("geonames_details") or {}
        if details.get("country_code"):
            return str(details["country_code"])
    return None


def lookup_ror(name: str, *, client: httpx.Client | None = None) -> dict | None:
    """Ask ROR to match one affiliation string. Returns the accepted match, or None.

    Only a `chosen` match is returned. ROR's own threshold is what separates "Technische
    Universität München" (chosen, 1.0) from "Wilhelmsgymnasium München" -> MTU Aero Engines
    (0.9, not chosen), so second-guessing it with our own cutoff would only add errors.
    """
    owned = client is None
    client = client or httpx.Client(timeout=ROR_TIMEOUT_SECONDS, follow_redirects=True)
    try:
        response = client.get(ROR_AFFILIATION_URL, params={"affiliation": name})
        response.raise_for_status()
        for item in response.json().get("items") or []:
            if item.get("chosen"):
                organization = item.get("organization") or {}
                ror_id = str(organization.get("id") or "").rstrip("/").split("/")[-1]
                if not ror_id:
                    return None
                return {
                    "ror_id": ror_id,
                    "name": _ror_display_name(organization),
                    "country_code": _ror_country(organization),
                    "score": item.get("score"),
                }
        return None
    finally:
        if owned:
            client.close()


def resolve_institution(
    db: Session, raw_name: str | None, *, client: httpx.Client | None = None
) -> Institution | None:
    """Get-or-create the institution for an affiliation string, caching the decision.

    Returns None when ROR has no confident match; that outcome is cached too, so the string is
    never sent again and stays queryable as an unresolved alias.
    """
    key = institution_key(raw_name)
    if key is None:
        return None
    assert raw_name is not None  # institution_key returns None for empty input

    cached = db.execute(
        select(InstitutionAlias).where(InstitutionAlias.alias_key == key)
    ).scalar_one_or_none()
    if cached is not None:
        return db.get(Institution, cached.institution_id) if cached.institution_id else None

    match = lookup_ror(raw_name, client=client)
    institution = None
    if match is not None:
        institution = db.execute(
            select(Institution).where(Institution.ror_id == match["ror_id"])
        ).scalar_one_or_none()
        if institution is None:
            institution = Institution(
                ror_id=match["ror_id"],
                name=match["name"] or raw_name.strip(),
                country_code=match["country_code"],
            )
            db.add(institution)
            db.flush()
    db.add(
        InstitutionAlias(
            alias_key=key,
            raw_name=raw_name.strip(),
            institution_id=institution.id if institution else None,
            match_score=match["score"] if match else None,
        )
    )
    db.flush()
    return institution
