"""Founder axis (prd item 3) — deterministic projection of the persistent Founder Score.

Pure-fn tests are DB-free; writer tests run against the real dev DB in a rolled-back
transaction (same pattern as test_loop_tables). No LLM anywhere on this axis.
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Claim, ClaimEvidence, Founder, Opportunity, ScoreHistory, Signal, ThreeAxis
from app.screening.founder_axis import (
    BEAR_BELOW,
    BULL_AT_LEAST,
    COLD_START_MIN_CLAIMS,
    compute_founder_axis,
    upsert_founder_axis,
)


def _claims(n: int, trust: float = 0.6) -> list[dict]:
    return [{"id": str(uuid.uuid4()), "trust": trust, "urls": []} for _ in range(n)]


# ── verdict bands ────────────────────────────────────────────────────────────


def test_verdict_bull_at_band():
    r = compute_founder_axis(
        founder_score=44.5, components={"tech": 33.4}, claims=_claims(22, 0.44), history_scores=[]
    )
    assert r.verdict == "bull"
    assert r.score == 44.5


def test_verdict_neutral_mid_band():
    r = compute_founder_axis(
        founder_score=22.1, components={"tech": 13.8}, claims=_claims(8, 0.5), history_scores=[]
    )
    assert r.verdict == "neutral"


def test_verdict_bear_needs_evidence():
    # low score + enough claims = genuinely weak public footprint -> bear
    r = compute_founder_axis(
        founder_score=13.5, components={"tech": 4.8}, claims=_claims(9, 0.34), history_scores=[]
    )
    assert r.verdict == "bear"


def test_cold_start_low_score_is_neutral_not_bear():
    # limited evidence != negative evidence: same low score, few claims -> neutral
    r = compute_founder_axis(
        founder_score=13.5,
        components={"pedigree": 13.5},
        claims=_claims(COLD_START_MIN_CLAIMS - 1, 0.5),
        history_scores=[],
    )
    assert r.verdict == "neutral"
    assert "cold-start" in r.rationale
    assert any("cold-start" in g for g in r.gaps)


def test_no_claims_is_neutral_with_gap():
    r = compute_founder_axis(founder_score=None, components=None, claims=[], history_scores=[])
    assert r.score is None
    assert r.verdict == "neutral"
    assert r.confidence == 0.0
    assert any("no claims" in g for g in r.gaps)


def test_band_constants_sane():
    assert 0 < BEAR_BELOW < BULL_AT_LEAST <= 100


# ── trend from score history ─────────────────────────────────────────────────


def test_trend_improving():
    r = compute_founder_axis(
        founder_score=20.0, components={}, claims=_claims(8), history_scores=[10.0, 20.0]
    )
    assert r.trend == "improving"


def test_trend_declining():
    r = compute_founder_axis(
        founder_score=20.0, components={}, claims=_claims(8), history_scores=[30.0, 20.0]
    )
    assert r.trend == "declining"


def test_trend_stable_within_deadband():
    r = compute_founder_axis(
        founder_score=20.5, components={}, claims=_claims(8), history_scores=[20.0, 20.5]
    )
    assert r.trend == "stable"


def test_trend_new_founder_defaults_stable_with_gap():
    for hist in ([], [15.0]):
        r = compute_founder_axis(
            founder_score=15.0, components={}, claims=_claims(8), history_scores=hist
        )
        assert r.trend == "stable"
        assert any("history" in g for g in r.gaps)


# ── confidence (deterministic, evidence-mass based) ──────────────────────────


def test_confidence_monotonic_in_evidence_and_capped():
    lo = compute_founder_axis(
        founder_score=10.0, components={}, claims=_claims(2, 0.5), history_scores=[]
    )
    mid = compute_founder_axis(
        founder_score=10.0, components={}, claims=_claims(8, 0.5), history_scores=[]
    )
    hi = compute_founder_axis(
        founder_score=10.0, components={}, claims=_claims(100, 0.9), history_scores=[]
    )
    assert lo.confidence < mid.confidence < hi.confidence <= 0.95


def test_cold_start_confidence_low():
    r = compute_founder_axis(
        founder_score=13.9,
        components={"pedigree": 13.9},
        claims=_claims(5, 0.54),
        history_scores=[],
    )
    assert r.confidence < 0.5


def test_score_with_claims_but_no_founder_score_fails_fast():
    with pytest.raises(RuntimeError, match="founder_score"):
        compute_founder_axis(
            founder_score=None, components=None, claims=_claims(3), history_scores=[]
        )


# ── writer: upsert three_axis axis='founder' against the real DB ─────────────


def test_upsert_founder_axis_real_db():
    db = SessionLocal()
    try:
        f = Founder(
            display_name="TEST-" + uuid.uuid4().hex,
            founder_score=44.5,
            components={"tech": 33.4, "pedigree": 12.5},
        )
        db.add(f)
        db.flush()
        sig = Signal(
            source="github",
            signal_type="repo",
            external_id="TEST-" + uuid.uuid4().hex,
            url="https://github.com/test/repo",
            founder_id=f.id,
        )
        db.add(sig)
        db.flush()
        claim_ids = []
        for i in range(7):
            cl = Claim(
                founder_id=f.id,
                category="open_source",
                statement=f"TEST claim {i}",
                trust_score=0.6,
            )
            db.add(cl)
            db.flush()
            claim_ids.append(str(cl.id))
            db.add(ClaimEvidence(claim_id=cl.id, signal_id=sig.id, stance="supports", weight=0.5))
        # explicit created_at: pg now() is txn-stable, same-txn rows would tie on ordering
        t1, t2 = datetime(2026, 7, 1, tzinfo=UTC), datetime(2026, 7, 15, tzinfo=UTC)
        db.add_all(
            [
                ScoreHistory(founder_id=f.id, score=30.0, created_at=t1),
                ScoreHistory(founder_id=f.id, score=44.5, created_at=t2),
            ]
        )
        opp = Opportunity(founder_id=f.id, idea="TEST idea", sector="devtools")
        db.add(opp)
        db.flush()

        row = upsert_founder_axis(db, opp.id)
        assert row.axis == "founder"
        assert row.verdict == "bull"
        assert row.trend == "improving"
        assert row.score == 44.5
        assert row.confidence is not None and row.confidence > 0.4
        assert row.evidence is not None
        assert set(row.evidence["claim_ids"]) == set(claim_ids)
        assert row.evidence["urls"] == ["https://github.com/test/repo"]

        # idempotent: second run updates the same row, no duplicate
        row2 = upsert_founder_axis(db, opp.id)
        db.flush()
        assert row2.id == row.id
        n = db.execute(
            select(ThreeAxis).where(
                ThreeAxis.opportunity_id == opp.id, ThreeAxis.axis == "founder"
            )
        ).scalars().all()
        assert len(n) == 1
    finally:
        db.rollback()
        db.close()


def test_upsert_founder_axis_founderless_opportunity_fails():
    db = SessionLocal()
    try:
        opp = Opportunity(founder_id=None, idea="TEST no founder", sector="ai")
        db.add(opp)
        db.flush()
        with pytest.raises(ValueError, match="no founder"):
            upsert_founder_axis(db, opp.id)
    finally:
        db.rollback()
        db.close()


def test_upsert_founder_axis_unknown_opportunity_fails():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError, match="not found"):
            upsert_founder_axis(db, uuid.uuid4())
    finally:
        db.rollback()
        db.close()
