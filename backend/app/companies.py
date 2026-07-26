"""Company resolution — one venture, one row.

Every writer that names a venture goes through `resolve_company`, so re-analysing a deal reuses
the existing row instead of minting a second one. Identity is decided by two deterministic keys:

  - `domain` — the registrable host of the website, the stronger key (a display name drifts:
    "Nimbus Edge" / "Nimbus Edge Technologies" / "Nimbus Edge GmbH" are one venture),
  - `name_key` — case/accent/spacing/legal-suffix-insensitive name, used when there is no site.

`link_founder_company` records founder <-> venture. Nothing wrote that table before, which left
"which ventures has this founder been part of" unanswerable — the exact question a Founder Score
that follows a person across startups has to answer.
"""

import uuid
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.entity_resolution import normalize_comparison_text
from app.models import Company, FounderCompany

# Legal-form tokens carry no identity: the same venture is written with and without them.
# Whole tokens only, so "Cointelegraph" or "Incode" are untouched.
_LEGAL_SUFFIXES = frozenset(
    {
        "gmbh", "ug", "ag", "kg", "ohg", "mbh", "eg",
        "ltd", "limited", "llc", "lp", "llp", "plc",
        "inc", "incorporated", "corp", "corporation", "co", "company",
        "bv", "nv", "sa", "sas", "sarl", "srl", "spa", "oyj", "oy", "ab", "as", "aps",
        "pte", "pty", "kk", "kft", "sro", "doo", "zoo",
    }
)  # fmt: skip


def company_name_key(name: str | None) -> str | None:
    """Deterministic dedup key for a venture name. None when there is no usable name."""
    tokens = normalize_comparison_text(name).split()
    if not tokens:
        return None
    stripped = [t for t in tokens if t not in _LEGAL_SUFFIXES]
    # A name consisting only of legal-form tokens keeps its identity rather than collapsing
    # to empty and colliding with every other such name.
    return " ".join(stripped or tokens)


def company_domain_key(website: str | None) -> str | None:
    """Registrable host, lowercased, without `www.`. None when there is no usable site."""
    raw = (website or "").strip()
    if not raw:
        return None
    parsed = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = parsed.netloc.casefold().removeprefix("www.").rstrip(".")
    return host or None


def resolve_company(
    db: Session,
    *,
    name: str | None = None,
    website: str | None = None,
    sector: str | None = None,
    geo: str | None = None,
    description: str | None = None,
) -> Company:
    """Get-or-create the venture. Domain wins over name; existing values are never overwritten."""
    name_key = company_name_key(name)
    domain = company_domain_key(website)
    if not name_key and not domain:
        raise ValueError("resolve_company requires a usable name or website")

    row = None
    if domain:
        row = db.execute(select(Company).where(Company.domain == domain)).scalars().first()
    if row is None and name_key:
        row = db.execute(select(Company).where(Company.name_key == name_key)).scalars().first()

    if row is None:
        row = Company(
            name=(name or "").strip() or None,
            name_key=name_key,
            website=(website or "").strip() or None,
            domain=domain,
            sector=sector,
            geo=geo,
            description=description,
        )
        db.add(row)
        db.flush()
        return row

    # Enrich only. What the venture already asserts is authoritative — a later, thinner mention
    # must not overwrite a better one.
    if row.name_key is None and name_key:
        row.name_key = name_key
    if row.domain is None and domain:
        row.domain = domain
    if not row.website and website:
        row.website = (website or "").strip() or None
    if not row.sector and sector:
        row.sector = sector
    if not row.geo and geo:
        row.geo = geo
    if not row.description and description:
        row.description = description
    return row


def link_founder_company(
    db: Session,
    founder_id: uuid.UUID,
    company_id: uuid.UUID,
    role: str | None = "founder",
) -> FounderCompany:
    """Idempotent founder <-> venture edge."""
    existing = (
        db.execute(
            select(FounderCompany).where(
                FounderCompany.founder_id == founder_id,
                FounderCompany.company_id == company_id,
            )
        )
        .scalars()
        .first()
    )
    if existing is not None:
        if role and not existing.role:
            existing.role = role
        return existing
    row = FounderCompany(founder_id=founder_id, company_id=company_id, role=role)
    db.add(row)
    db.flush()
    return row
