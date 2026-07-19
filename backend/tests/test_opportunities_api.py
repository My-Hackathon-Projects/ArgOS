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


def test_get_missing_memo_for_existing_opportunity_returns_null(client):
    c, _ = client
    r = c.post("/opportunities", json={"idea": "TEST memo pending"})
    opp_id = r.json()["id"]

    r = c.get(f"/opportunities/{opp_id}/memo")
    assert r.status_code == 200
    assert r.json() is None


def test_get_unknown_opportunity_404(client):
    c, _ = client
    r = c.get(f"/opportunities/{uuid.uuid4()}")
    assert r.status_code == 404
    assert r.json()["detail"] == "opportunity not found"


def test_decide_pursue_stamps_latency(client):
    c, _ = client
    r = c.post("/opportunities", json={"idea": "TEST decide pursue"})
    created = r.json()
    # No founder → the creation itself starts the latency clock.
    assert created["first_signal_at"] is not None
    assert created["decision"] is None

    r = c.post(f"/opportunities/{created['id']}/decision", json={"decision": "pursue"})
    assert r.status_code == 200, r.text
    decided = r.json()
    assert decided["status"] == "decided"
    assert decided["decision"] == "pursue"
    assert decided["decided_at"] is not None
    assert decided["signal_to_decision_seconds"] is not None
    assert decided["signal_to_decision_seconds"] >= 0


def test_decide_pass_rejects(client):
    c, _ = client
    r = c.post("/opportunities", json={"idea": "TEST decide pass"})
    opp_id = r.json()["id"]
    r = c.post(f"/opportunities/{opp_id}/decision", json={"decision": "pass"})
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"
    assert r.json()["decision"] == "pass"


def test_decide_invalid_verdict_422(client):
    c, _ = client
    r = c.post("/opportunities", json={"idea": "TEST decide invalid"})
    opp_id = r.json()["id"]
    r = c.post(f"/opportunities/{opp_id}/decision", json={"decision": "maybe"})
    assert r.status_code == 422


def test_decide_unknown_opportunity_404(client):
    c, _ = client
    r = c.post(f"/opportunities/{uuid.uuid4()}/decision", json={"decision": "track"})
    assert r.status_code == 404


def test_first_signal_at_uses_earliest_founder_signal(client):
    c, session = client
    f = Founder(display_name="TEST-latency-" + uuid.uuid4().hex)
    session.add(f)
    session.flush()
    from datetime import UTC, datetime

    from app.models import Signal

    old = datetime(2024, 3, 1, tzinfo=UTC)
    session.add(
        Signal(
            source="synthetic",
            signal_type="post",
            external_id="TEST-" + uuid.uuid4().hex,
            founder_id=f.id,
            occurred_at=old,
        )
    )
    session.flush()

    r = c.post("/opportunities", json={"founder_id": str(f.id), "idea": "TEST latency clock"})
    assert r.status_code == 201
    assert r.json()["first_signal_at"] is not None
    assert r.json()["first_signal_at"].startswith("2024-03-01")
