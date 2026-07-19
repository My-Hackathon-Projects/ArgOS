"""Opportunity endpoints (prd item 4) — manual-dispatch entry for screening/memo.

TestClient against the real app + real dev DB, with get_db overridden to a savepoint-joined
session so handler commits stay inside an outer transaction that rolls back — nothing persists.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db import engine
from app.main import app
from app.models import Founder, ThreeAxis


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


def test_create_then_get_round_trip(client):
    c, _ = client
    payload = {
        "company_name": "Test Robotics",
        "idea": "TEST autonomous warehouse robots " + uuid.uuid4().hex,
        "sector": "robotics",
        "geo": "EU",
    }
    r = c.post("/opportunities", json=payload)
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["status"] == "screening"
    assert created["idea"] == payload["idea"]
    assert created["axes"] == []

    r = c.get(f"/opportunities/{created['id']}")
    assert r.status_code == 200
    got = r.json()
    assert got["id"] == created["id"]
    assert got["company_name"] == "Test Robotics"
    assert got["sector"] == "robotics"


def test_create_missing_idea_and_sector_422(client):
    c, _ = client
    r = c.post("/opportunities", json={"company_name": "No Subject Inc", "geo": "US"})
    assert r.status_code == 422
    # whitespace-only doesn't count as a subject either
    r = c.post("/opportunities", json={"idea": "   ", "sector": ""})
    assert r.status_code == 422


def test_create_sector_only_ok(client):
    c, _ = client
    r = c.post("/opportunities", json={"sector": "fintech"})
    assert r.status_code == 201
    assert r.json()["idea"] is None


def test_create_unknown_founder_404(client):
    c, _ = client
    r = c.post("/opportunities", json={"idea": "x", "founder_id": str(uuid.uuid4())})
    assert r.status_code == 404
    assert r.json()["detail"] == "founder not found"


def test_create_with_founder_and_list(client):
    c, session = client
    f = Founder(display_name="TEST-" + uuid.uuid4().hex)
    session.add(f)
    session.flush()

    r = c.post("/opportunities", json={"founder_id": str(f.id), "idea": "TEST founder-linked"})
    assert r.status_code == 201
    opp_id = r.json()["id"]
    assert r.json()["founder_id"] == str(f.id)

    r = c.get("/opportunities")
    assert r.status_code == 200
    assert opp_id in [o["id"] for o in r.json()]


def test_get_includes_axes_summary(client):
    c, session = client
    r = c.post("/opportunities", json={"idea": "TEST with axis"})
    opp_id = r.json()["id"]

    session.add(
        ThreeAxis(
            opportunity_id=uuid.UUID(opp_id),
            axis="market",
            score=61.0,
            verdict="neutral",
            trend="stable",
            confidence=0.7,
            rationale="TEST",
        )
    )
    session.flush()

    r = c.get(f"/opportunities/{opp_id}")
    assert r.status_code == 200
    axes = r.json()["axes"]
    assert len(axes) == 1
    assert axes[0]["axis"] == "market"
    assert axes[0]["verdict"] == "neutral"
    assert axes[0]["trend"] == "stable"


def test_get_unknown_opportunity_404(client):
    c, _ = client
    r = c.get(f"/opportunities/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "opportunity not found"
