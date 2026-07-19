"""Eval-bed resolution (prd item 1): the FIXED subjects resolve in the real dev DB and the
bed keeps its coverage properties (strong + cold-start founder, founder-linked opportunity).
Read-only against the shared dev DB — validates the actual bed, no synthetic rows.
"""

import uuid

import pytest

from app.db import SessionLocal
from app.eval.subjects import FOUNDER_SUBJECTS, OPPORTUNITY_SUBJECTS, Subject, validate_subjects

pytestmark = pytest.mark.dev_bed


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


def test_bed_resolves_with_coverage(db):
    summary = validate_subjects(db)

    assert len(summary["founders"]) == len(FOUNDER_SUBJECTS)
    assert len(summary["opportunities"]) == len(OPPORTUNITY_SUBJECTS)
    assert any(f["cold_start"] for f in summary["founders"])
    assert any(not f["cold_start"] for f in summary["founders"])
    assert all(f["n_claims"] > 0 for f in summary["founders"])
    assert any(o["founder_id"] is not None for o in summary["opportunities"])
    assert any(o["founder_id"] is None for o in summary["opportunities"])
    assert all(
        (o["idea"] or "").strip() or (o["sector"] or "").strip() for o in summary["opportunities"]
    )
    # Bed currently has no contradiction case (tracked in human-backlog); the flag must
    # exist so item-2's scorecard surfaces it every round.
    assert summary["has_contradiction_subject"] is False


def test_missing_founder_crashes(db):
    ghost = Subject(uuid.uuid4(), "Ghost", "does not exist")
    with pytest.raises(RuntimeError, match="not in DB"):
        validate_subjects(db, founders=(ghost,) + FOUNDER_SUBJECTS[1:])


def test_missing_opportunity_crashes(db):
    ghost = Subject(uuid.uuid4(), "Ghost Opp", "does not exist")
    with pytest.raises(RuntimeError, match="not in DB"):
        validate_subjects(db, opportunities=(ghost,) + OPPORTUNITY_SUBJECTS[1:])


def test_dropping_cold_start_founder_breaks_coverage(db):
    strong_only = tuple(s for s in FOUNDER_SUBJECTS if s.label != "Tanmay Baranwal")
    with pytest.raises(RuntimeError, match="cold-start"):
        validate_subjects(db, founders=strong_only)
