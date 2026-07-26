"""Founder-first, enforced rather than intended.

The product rule is that a deal is a *person* plus what they are building: the Founder Score is
per-person, persistent, and follows them across startups. A deal with no founder cannot be
screened on the founder axis, cannot carry a score, and cannot be decided.

Nothing enforced it. `opportunity.founder_id` was nullable, `POST /opportunities` accepted a
missing founder, and the market path could mint a company-first deal from a bare dict — which is
how the dev DB acquired three founderless rows.

Two changes hold the rule now:
  - `opportunity.founder_id` is NOT NULL,
  - the market path can only *enrich* an existing deal. It never creates one, so a market
    analysis cannot introduce a company-first opportunity by side effect.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from helpers import unique_suffix
from sqlalchemy import text

from app.companies import resolve_company
from app.db import SessionLocal
from app.main import app
from app.market.persist import persist_market
from app.market.service import run_market_analysis
from app.models import Founder, Opportunity


def _market_analysis(company_name: str, suffix: str) -> dict:
    url = f"https://example.test/mkt/{suffix}"
    return {
        "opportunity": {
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


def test_opportunity_requires_a_founder() -> None:
    """A founderless deal is not representable."""
    db = SessionLocal()
    try:
        db.add(Opportunity(idea="an idea with nobody behind it", status="screening"))
        with pytest.raises(Exception, match="founder_id"):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_market_persist_cannot_create_a_deal() -> None:
    """The market writer enriches; it never introduces a company-first opportunity."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        with pytest.raises(ValueError, match="opportunity_id"):
            persist_market(db, _market_analysis(f"Ghostco {suffix}", suffix))
    finally:
        db.rollback()
        db.close()


def test_market_service_cannot_create_a_deal() -> None:
    """Same rule one layer up — no bare-dict entry point survives."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        assert suffix  # the bare-dict creation mode no longer exists as a parameter at all
        with pytest.raises(ValueError, match="opportunity_id"):
            run_market_analysis(db)
    finally:
        db.rollback()
        db.close()


def test_market_persist_enriches_an_existing_deal() -> None:
    """The supported path: an existing founder-backed deal gains a market axis."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Grace Market {suffix}", status="candidate")
        db.add(founder)
        db.flush()
        name = f"Nimbus {suffix}"
        company = resolve_company(db, name=name)
        opp = Opportunity(
            founder_id=founder.id,
            company_id=company.id,
            company_name=name,
            idea="agent orchestration",
            status="diligence",
        )
        db.add(opp)
        db.flush()

        result = persist_market(db, _market_analysis(name, suffix), opportunity_id=opp.id)
        assert result["opportunity_id"] == str(opp.id)
        assert result["market_axis"]["verdict"] == "bull"
    finally:
        db.close()


def test_create_opportunity_api_rejects_a_missing_founder() -> None:
    """The API contract carries the rule too, so a client cannot ask for a founderless deal."""
    with TestClient(app) as client:
        r = client.post("/opportunities", json={"company_name": "Nobody Inc", "idea": "x"})
        assert r.status_code == 422, r.text


def test_create_opportunity_api_rejects_an_unknown_founder() -> None:
    with TestClient(app) as client:
        r = client.post(
            "/opportunities",
            json={"founder_id": str(uuid.uuid4()), "company_name": "Nobody Inc", "idea": "x"},
        )
        assert r.status_code == 404, r.text


def test_create_opportunity_api_accepts_a_founder_backed_deal() -> None:
    db = SessionLocal()
    try:
        founder = Founder(display_name=f"Ada Api {unique_suffix()}", status="candidate")
        db.add(founder)
        db.commit()
        founder_id = str(founder.id)
    finally:
        db.close()
    with TestClient(app) as client:
        r = client.post(
            "/opportunities",
            json={
                "founder_id": founder_id,
                "company_name": f"Apico {unique_suffix()}",
                "idea": "x",
            },
        )
        assert r.status_code == 201, r.text
        assert r.json()["founder_id"] == founder_id


@pytest.mark.dev_bed
def test_no_founderless_deals_in_the_bed(dev_db) -> None:
    orphans = dev_db.execute(
        text("SELECT id, company_name FROM opportunity WHERE founder_id IS NULL")
    ).all()
    assert not orphans, f"founderless deals: {orphans}"
