"""`company` is the single source of truth for a venture.

Three defects motivated this:
  - the market writer minted a fresh `Company` on every run, so re-analysing one deal produced
    duplicate rows for the same venture (the dev DB held two "Nimbus Edge"),
  - `founder_company` was never written by any path — 0 rows — so "which ventures has this
    founder been part of" was unanswerable, which is precisely what a Founder Score that
    "follows them across startups" depends on,
  - two writers set `opportunity.company_name` without ever creating a `company`, so a named
    venture could exist with no row to point at.

The invariant enforced here is "a *named* venture has exactly one company row", not "every deal
has a company". An idea-stage deal legitimately has no company yet; forcing one would mint
placeholder rows with no name and pollute the table this change exists to protect. The named
case IS expressible as a single-table CHECK, so it is one:

    CHECK (company_name IS NULL OR company_id IS NOT NULL)
"""

import uuid

import pytest
from helpers import unique_suffix
from sqlalchemy import func, select, text

from app.companies import company_name_key, link_founder_company, resolve_company
from app.db import SessionLocal
from app.market.persist import persist_market
from app.models import Company, Founder, FounderCompany, Opportunity


def _market_analysis(founder_id: uuid.UUID | None, company_name: str, suffix: str) -> dict:
    url = f"https://example.test/market/{suffix}"
    return {
        "opportunity": {
            "founder_id": str(founder_id) if founder_id else None,
            "company_name": company_name,
            "idea": "agent orchestration",
            "sector": "devtools",
            "geo": "EU",
        },
        "hits_by_goal": {
            "sizing": [{"url": url, "title": "Market report", "content": "TAM is large."}]
        },
        "sizing": {
            "figures": [
                {
                    "metric": "TAM",
                    "value": "$1B",
                    "unit": "USD",
                    "basis": "report",
                    "citation_indices": [0],
                    "confidence": 0.8,
                }
            ]
        },
        "synthesis": {
            "axis": {"score": 70, "verdict": "bull", "rationale": "r", "confidence": 0.7},
            "gaps": [],
        },
    }


def test_company_name_key_ignores_case_spacing_and_legal_suffix() -> None:
    """The dedup key is what makes 'one venture, one row' decidable."""
    assert company_name_key("Nimbus Edge") == company_name_key("  NIMBUS   edge ")
    assert company_name_key("Nimbus Edge GmbH") == company_name_key("Nimbus Edge")
    assert company_name_key("Nimbus Edge, Inc.") == company_name_key("Nimbus Edge")
    assert company_name_key("Café Ventures") == company_name_key("Cafe Ventures")
    assert company_name_key(None) is None
    assert company_name_key("   ") is None
    # distinct ventures stay distinct
    assert company_name_key("Nimbus Edge") != company_name_key("Nimbus Ridge")
    # a name that is *only* a legal suffix keeps its identity rather than collapsing to empty
    assert company_name_key("GmbH") == "gmbh"


def test_resolve_company_is_idempotent() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        a = resolve_company(db, name=f"Nimbus {suffix}")
        db.flush()
        b = resolve_company(db, name=f"  nimbus {suffix}  GmbH ")
        db.flush()
        assert a.id == b.id
        n = db.execute(
            select(func.count()).select_from(Company).where(Company.name_key == a.name_key)
        ).scalar_one()
        assert n == 1
    finally:
        db.rollback()
        db.close()


def test_resolve_company_matches_on_domain_when_name_differs() -> None:
    """A website is a stronger identity key than a display name."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        site = f"https://www.{suffix}.example.test/"
        a = resolve_company(db, name=f"Nimbus {suffix}", website=site)
        db.flush()
        b = resolve_company(
            db, name=f"Nimbus {suffix} Technologies", website=f"{suffix}.example.test"
        )
        db.flush()
        assert a.id == b.id
    finally:
        db.rollback()
        db.close()


def test_resolve_company_backfills_missing_fields_without_overwriting() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        a = resolve_company(db, name=f"Nimbus {suffix}", sector="devtools")
        db.flush()
        resolve_company(db, name=f"Nimbus {suffix}", sector="fintech", geo="EU")
        db.flush()
        db.refresh(a)
        assert a.sector == "devtools", "existing values are authoritative, not overwritten"
        assert a.geo == "EU", "blank fields are filled in"
    finally:
        db.rollback()
        db.close()


def test_link_founder_company_is_idempotent() -> None:
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Ada Link {suffix}", status="candidate")
        db.add(founder)
        db.flush()
        company = resolve_company(db, name=f"Nimbus {suffix}")
        db.flush()
        link_founder_company(db, founder.id, company.id)
        db.flush()
        link_founder_company(db, founder.id, company.id)
        db.flush()
        n = db.execute(
            select(func.count())
            .select_from(FounderCompany)
            .where(FounderCompany.founder_id == founder.id)
        ).scalar_one()
        assert n == 1
    finally:
        db.rollback()
        db.close()


def test_market_writer_reuses_company_and_records_the_founder_link() -> None:
    """Re-analysing a deal must not mint a second venture, and must record founder<->company."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        name = f"Nimbus {suffix}"
        founder = Founder(display_name=f"Grace Co {suffix}", status="candidate")
        db.add(founder)
        db.flush()

        persist_market(db, _market_analysis(founder.id, name, suffix))
        persist_market(db, _market_analysis(founder.id, name, unique_suffix()))

        key = company_name_key(name)
        companies = db.execute(select(Company).where(Company.name_key == key)).scalars().all()
        assert len(companies) == 1, "second analysis minted a duplicate venture"

        links = (
            db.execute(select(FounderCompany).where(FounderCompany.company_id == companies[0].id))
            .scalars()
            .all()
        )
        assert len(links) == 1
        assert links[0].founder_id == founder.id
    finally:
        db.close()


def test_named_opportunity_must_point_at_a_company() -> None:
    """The CHECK: a named venture with no company row is not representable."""
    db = SessionLocal()
    try:
        db.add(Opportunity(company_name="Orphan Venture", idea="x", status="screening"))
        with pytest.raises(Exception, match="ck_opportunity_named_company"):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_idea_stage_opportunity_needs_no_company() -> None:
    """An idea-stage deal is still legal — the rule is about *named* ventures."""
    db = SessionLocal()
    try:
        founder = Founder(display_name=f"Alan Idea {unique_suffix()}", status="candidate")
        db.add(founder)
        db.flush()
        opp = Opportunity(founder_id=founder.id, idea="an unnamed idea", status="screening")
        db.add(opp)
        db.flush()
        assert opp.company_id is None and opp.company_name is None
    finally:
        db.rollback()
        db.close()


@pytest.mark.dev_bed
def test_no_duplicate_ventures_in_the_bed(dev_db) -> None:
    dupes = dev_db.execute(
        text(
            "SELECT name_key, count(*) FROM company WHERE name_key IS NOT NULL "
            "GROUP BY name_key HAVING count(*) > 1"
        )
    ).all()
    assert not dupes, f"duplicate ventures: {dupes}"


@pytest.mark.dev_bed
def test_every_named_deal_has_a_company_in_the_bed(dev_db) -> None:
    orphans = dev_db.execute(
        text(
            "SELECT id, company_name FROM opportunity "
            "WHERE company_name IS NOT NULL AND company_id IS NULL"
        )
    ).all()
    assert not orphans, f"named deals with no company row: {orphans}"
