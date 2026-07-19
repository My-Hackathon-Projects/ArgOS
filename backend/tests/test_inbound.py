"""Inbound intake (/apply) — deck parsing, hard filter, and the intake round trip.

LLM steps are monkeypatched at the service seam (extract_deck / prescreen_llm); everything
else (opportunity, signals, claims, evidence, trust, trace) runs for real against the dev DB
inside the savepoint-rollback fixture.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db import engine
from app.inbound.deck import DECK_SOURCE_RELIABILITY, parse_deck
from app.inbound.extract import DeckClaim, DeckExtraction, PreScreenResult
from app.inbound.service import hard_filter
from app.main import app
from app.models import Claim, ClaimEvidence, InvestmentThesis, Opportunity, Signal, TraceStep


def _pdf(pages: list[str]) -> bytes:
    import fitz

    doc = fitz.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


@pytest.fixture()
def client():
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")

    from app.db import get_db

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), session
    finally:
        app.dependency_overrides.clear()
        session.close()
        outer.rollback()
        conn.close()


# ── parse_deck ───────────────────────────────────────────────────────────────
def test_parse_deck_pages():
    opp_id = uuid.uuid4()
    envs = parse_deck(_pdf(["We have $50K MRR", "Team: ex-Google"]), "Acme", opp_id)
    assert len(envs) == 2
    assert envs[0].source == "inbound"
    assert envs[0].signal_type == "deck"
    assert envs[0].external_id == f"deck:{opp_id}:p1"
    assert envs[1].external_id == f"deck:{opp_id}:p2"
    assert "$50K MRR" in envs[0].raw["text"]
    assert envs[0].raw["page"] == 1
    assert envs[0].entity_hint == "Acme"
    assert envs[0].source_reliability == DECK_SOURCE_RELIABILITY


def test_parse_deck_empty_bytes_raises():
    with pytest.raises(ValueError, match="empty"):
        parse_deck(b"", "Acme", uuid.uuid4())


def test_parse_deck_no_text_raises():
    with pytest.raises(ValueError, match="no extractable text"):
        parse_deck(_pdf([""]), "Acme", uuid.uuid4())


# ── hard_filter ──────────────────────────────────────────────────────────────
def test_hard_filter_rejects_off_thesis_sector():
    thesis = InvestmentThesis(industries=["fintech", "healthcare"], geo=["EU"])
    r = hard_filter(thesis, "gambling", "EU")
    assert r is not None and r.verdict == "reject"
    assert "sector" in r.reason


def test_hard_filter_loose_match_and_missing_values_pass():
    thesis = InvestmentThesis(industries=["healthcare"], geo=["EU"])
    assert hard_filter(thesis, "healthtech, healthcare AI", "EU") is None  # substring match
    assert hard_filter(thesis, None, None) is None  # unknown sector/geo -> no hard call
    assert hard_filter(None, "gambling", "US") is None  # no thesis -> no filter


# ── /apply round trip (LLMs monkeypatched) ───────────────────────────────────
def _fake_extraction(*_args, **_kwargs):
    return DeckExtraction(
        idea="TEST warehouse robots",
        sector="robotics",
        geo="EU",
        claims=[
            DeckClaim(category="revenue", statement="$50K MRR", source_page=1),
            DeckClaim(category="team", statement="ex-Google founding team", source_page=2),
            DeckClaim(category="traction", statement="hallucinated page", source_page=99),
        ],
    )


def _no_default_thesis(session):
    # The dev DB's default thesis would hard-filter the fake sector; these tests exercise
    # the LLM-prescreen seam, and hard_filter has its own unit tests above.
    session.execute(update(InvestmentThesis).values(is_default=False))
    session.flush()


def test_apply_round_trip(client, monkeypatch):
    c, session = client
    _no_default_thesis(session)
    monkeypatch.setattr("app.inbound.service.extract_deck", _fake_extraction)
    monkeypatch.setattr(
        "app.inbound.service.prescreen_llm",
        lambda *_a, **_k: PreScreenResult(verdict="pass", reason="TEST viable"),
    )

    r = c.post(
        "/apply",
        files={"deck": ("deck.pdf", _pdf(["$50K MRR", "Team"]), "application/pdf")},
        data={"company_name": "TEST Robotics " + uuid.uuid4().hex},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "screening"
    assert body["prescreen_verdict"] == "pass"
    assert body["signals_ingested"] == 2
    assert body["claims_minted"] == 2  # p.99 citation dropped (anti-hallucination)
    assert body["idea"] == "TEST warehouse robots"

    opp_id = uuid.UUID(body["opportunity_id"])
    opp = session.get(Opportunity, opp_id)
    assert opp.source == "inbound" and opp.sector == "robotics"

    claims = session.execute(select(Claim).where(Claim.opportunity_id == opp_id)).scalars().all()
    assert len(claims) == 2
    for cl in claims:
        assert cl.status == "unverified"  # single low-reliability source
        assert 0 < cl.trust_score < 0.7
        assert cl.attributes["source_pointer"].startswith("deck p.")
        edges = (
            session.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == cl.id))
            .scalars()
            .all()
        )
        assert len(edges) == 1 and edges[0].stance == "supports"
        sig = session.get(Signal, edges[0].signal_id)
        assert sig.source == "inbound" and sig.signal_type == "deck"

    trace = (
        session.execute(select(TraceStep).where(TraceStep.opportunity_id == opp_id))
        .scalars()
        .all()
    )
    assert len(trace) == 1
    assert trace[0].agent == "inbound_intake"
    assert trace[0].output["prescreen"] == "pass"
    assert trace[0].output["claims_dropped"] == 1


def test_apply_reject_keeps_evidence(client, monkeypatch):
    c, session = client
    _no_default_thesis(session)
    monkeypatch.setattr("app.inbound.service.extract_deck", _fake_extraction)
    monkeypatch.setattr(
        "app.inbound.service.prescreen_llm",
        lambda *_a, **_k: PreScreenResult(verdict="reject", reason="TEST off-thesis"),
    )

    r = c.post(
        "/apply",
        files={"deck": ("deck.pdf", _pdf(["content"]), "application/pdf")},
        data={"company_name": "TEST Reject " + uuid.uuid4().hex},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "rejected"
    assert body["prescreen_reason"] == "TEST off-thesis"

    opp_id = uuid.UUID(body["opportunity_id"])
    assert session.get(Opportunity, opp_id).status == "rejected"
    # rejected != deleted — claims + signals stay queryable
    n_claims = len(
        session.execute(select(Claim).where(Claim.opportunity_id == opp_id)).scalars().all()
    )
    assert n_claims >= 1


def test_apply_non_pdf_415(client):
    c, _ = client
    r = c.post(
        "/apply",
        files={"deck": ("deck.txt", b"hello", "text/plain")},
        data={"company_name": "X"},
    )
    assert r.status_code == 415


def test_apply_empty_file_422(client):
    c, _ = client
    r = c.post(
        "/apply",
        files={"deck": ("deck.pdf", b"", "application/pdf")},
        data={"company_name": "X"},
    )
    assert r.status_code == 422
