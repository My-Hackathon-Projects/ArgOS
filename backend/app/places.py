"""The single writer of a founder's place — and the evidence it resolves with.

A founder's location is six columns that only mean anything together: `raw_location` (what the
source said), `city`/`city_key`/`city_geonameid`/`country_code` (what it resolved to), and
`location_quality` (how it was matched). Three call sites wrote them and each wrote a different
subset — the enrichment path in `sourcing.persist` set `.city` alone and left the place id, key,
country and quality NULL, which defeats every place invariant in `maintenance.audit_identity` and
leaves a city string that `place_key` cannot compare. One writer, one rule, all six columns.

The evidence is the founder's own affiliation. `normalize_location` on a bare "Cambridge" is a
coin-flip between England and Massachusetts, but a founder whose institution resolved to a UK ROR
id is not ambiguous — and the join needs no new schema:

    founder.education[].school -> institution_key() -> institution_alias.alias_key
                               -> institution.country_code

Measured over the 508 live founders: 195 have institutions that agree on one country (88 of them
currently have no city at all), 55 have institutions in two or more countries, 24 have affiliations
ROR never resolved, and 234 have no education on record. Disagreement yields no hint at all rather
than a majority vote: evidence that contradicts itself is not evidence, and the fallback is the
existing population/prior cascade, not nothing.

Deliberately NOT used here: `thesis.geo`. It is a downstream matching filter, not a sourcing scope,
and resolving places through it would bias exactly the non-European founders the fund collects on
purpose — 50 of the ones with a derivable institution country are outside Europe.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.institutions import institution_key
from app.models import Founder, Institution, InstitutionAlias
from app.normalize import NormalizedLocation, normalize_location


def institution_country_index(db: Session) -> dict[str, str]:
    """`alias_key -> country_code` for every affiliation string ROR has resolved.

    Built once by a caller sweeping many founders; `reconcile_founders` touches all 508 and would
    otherwise issue a query per person.
    """
    rows = db.execute(
        select(InstitutionAlias.alias_key, Institution.country_code).join(
            Institution, InstitutionAlias.institution_id == Institution.id
        )
    ).all()
    return {alias_key: country for alias_key, country in rows if country}


def institution_country(
    db: Session, founder: Founder, *, index: dict[str, str] | None = None
) -> str | None:
    """The country the founder's affiliations agree on, or None when they do not."""
    if index is None:
        index = institution_country_index(db)
    countries = {
        country
        for entry in founder.education or []
        if isinstance(entry, dict)
        and (key := institution_key(entry.get("school")))
        and (country := index.get(key))
    }
    return countries.pop() if len(countries) == 1 else None


def apply_location(
    db: Session,
    founder: Founder,
    raw: str | None = None,
    *,
    institutions: dict[str, str] | None = None,
) -> NormalizedLocation:
    """Resolve `raw` against the founder's own context and write all six place columns.

    `raw` is a source string. When it is None the stored `raw_location` is re-resolved, which is
    what a re-run does after the gazetteer or the founder's affiliations have improved. It falls
    back to `raw_location` and never to `city`: `city` is derived, and promoting it back into the
    provenance column would launder a value this module produced into something a source said.
    """
    source_text = raw if raw and raw.strip() else None
    location = normalize_location(
        source_text or founder.raw_location,
        country_hint=institution_country(db, founder, index=institutions),
    )
    if source_text is not None:
        founder.raw_location = location.raw_location
    founder.city = location.city
    founder.city_key = location.city_key
    founder.city_geonameid = location.geonameid
    founder.country_code = location.country_code
    founder.location_quality = location.quality
    return location
