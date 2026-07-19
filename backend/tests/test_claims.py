"""Claim-layer tests: deterministic Trust/Founder-Score math + the dedup-key idempotency guard.

No LLM calls. The math tests are pure; the idempotency test creates its own rows in a
transaction and rolls back, so it's safe against a concurrently-used dev DB.
"""

import uuid

import pytest
from sqlalchemy import func, select

from app.claims import score, trust
from app.claims.schemas import ExtractedClaim
from app.claims.service import _mint
from app.db import SessionLocal
from app.models import Claim, ClaimEvidence, Founder, Signal

# ── Trust Score (noisy-OR, deterministic) ────────────────────────────────────


def test_evidence_weight_is_product_and_clamped():
    assert trust.evidence_weight(1.0, 1.0, 1.0) == 1.0
    assert trust.evidence_weight(0.9, 0.9, 0.85) == pytest.approx(0.6885)
    assert trust.evidence_weight(None, None, None) > 0.0  # defaults, never a silent zero


def test_corroboration_lifts_trust():
    assert trust.trust_score([0.9], []) == pytest.approx(0.9)
    assert trust.trust_score([0.5, 0.5, 0.5], []) == pytest.approx(0.875)  # 1 - 0.5^3
    assert trust.trust_score([0.5, 0.5, 0.5], []) > trust.trust_score([0.5], [])


def test_refutation_pulls_down_multiplicatively():
    base = trust.trust_score([0.9], [])
    weak = trust.trust_score([0.9], [0.2])
    strong = trust.trust_score([0.9], [0.9])
    assert strong < weak < base
    assert strong == pytest.approx(0.09, abs=0.005)  # 0.9 * (1 - 0.9)


def test_status_thresholds():
    assert trust.derive_status(0.8, []) == "verified"
    assert trust.derive_status(0.5, []) == "unverified"
    assert trust.derive_status(0.8, [0.6]) == "contradicted"  # strong refute overrides


# ── Founder Score (saturating aggregate) ─────────────────────────────────────


def test_impact_weighting_beats_volume():
    strong = [{"trust": 0.9, "impact": 0.9, "category": "research", "occurred_at": None}] * 3
    busy = [{"trust": 0.5, "impact": 0.2, "category": "media", "occurred_at": None}] * 30
    s_strong, comp = score.founder_score(strong)
    s_busy, _ = score.founder_score(busy)
    assert 0.0 <= s_busy <= 100.0 and 0.0 <= s_strong <= 100.0
    assert s_strong > s_busy  # 3 stellar claims out-score 30 mediocre ones
    assert set(comp) >= {"tech", "execution", "pedigree", "influence", "momentum"}


def test_recency_decays_but_stays_positive():
    from datetime import UTC, datetime

    now = datetime(2026, 7, 1, tzinfo=UTC)
    recent = score.recency_factor(datetime(2026, 6, 1, tzinfo=UTC), now)
    old = score.recency_factor(datetime(2021, 1, 1, tzinfo=UTC), now)
    assert 0.0 < old < recent <= 1.0


# ── Idempotency: a reused (non-identifying) dedup_key must NOT crash the insert ─
# Regression for uq_claim_founder_dedup: the LLM sometimes gives two DISTINCT facts
# the same page URL as dedup_key. Both claims must persist; the spurious key is dropped.


def test_mint_drops_colliding_dedup_key():
    db = SessionLocal()
    try:
        f = Founder(display_name="TEST-" + uuid.uuid4().hex)
        db.add(f)
        db.flush()
        s = Signal(
            source="web",
            signal_type="profile",
            external_id="t:" + uuid.uuid4().hex,
            canonical_url="https://t/" + uuid.uuid4().hex,
            founder_id=f.id,
            source_reliability=0.6,
            resolution_confidence=0.9,
        )
        db.add(s)
        db.flush()

        seen: set = set()
        used: set = set()
        key = "https://example.com/shared-profile-page"
        c1 = _mint(
            db,
            f.id,
            ExtractedClaim(
                statement="Role A",
                category="employment",
                impact=0.5,
                dedup_key=key,
                supporting_signals=[0],
            ),
            [s],
            seen,
            used,
        )
        c2 = _mint(
            db,
            f.id,
            ExtractedClaim(
                statement="Role B",
                category="employment",
                impact=0.5,
                dedup_key=key,
                supporting_signals=[0],
            ),
            [s],
            seen,
            used,
        )
        db.flush()  # WITHOUT the guard this raises UniqueViolation on uq_claim_founder_dedup

        assert c1.dedup_key == key and c2.dedup_key is None  # both kept, spurious key dropped
        assert (
            db.execute(
                select(func.count()).select_from(Claim).where(Claim.founder_id == f.id)
            ).scalar_one()
            == 2
        )
        assert (
            db.execute(
                select(func.count())
                .select_from(ClaimEvidence)
                .where(ClaimEvidence.claim_id == c1.id)
            ).scalar_one()
            == 1
        )
    finally:
        db.rollback()  # never persist test rows into the shared dev DB
        db.close()
