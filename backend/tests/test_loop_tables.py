"""Loop-table schema tests (item 1): score_history / memo / trace_step round-trip.

Exercises the 0006 tables + their ORM classes through the REAL dev DB in a transaction that
rolls back, so nothing persists (same pattern as test_claims.test_mint_drops_colliding_dedup_key).
No LLM. Proves the migration applied and the FKs / JSONB columns map correctly.
"""

import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Founder, Memo, Opportunity, ScoreHistory, TraceStep


def test_loop_tables_round_trip():
    db = SessionLocal()
    try:
        f = Founder(display_name="TEST-" + uuid.uuid4().hex, founder_score=42.0)
        db.add(f)
        db.flush()

        opp = Opportunity(founder_id=f.id, idea="TEST idea " + uuid.uuid4().hex, sector="ai")
        db.add(opp)
        db.flush()

        sh = ScoreHistory(
            founder_id=f.id,
            score=42.0,
            components={"tech": 0.4, "execution": 0.3},
            trigger_claim_id=None,  # nullable FK — a bootstrap point has no trigger
        )
        memo = Memo(
            opportunity_id=opp.id,
            sections={"Company snapshot": "TEST prose"},
            recommendation="pass",
            confidence=0.6,
            gaps=["Cap table: not disclosed"],
            quality={"anchors_pass": True, "judge_mean": 0.85},
        )
        step = TraceStep(
            opportunity_id=opp.id,
            founder_id=f.id,
            stage="score_founder",
            agent="founder_axis",
            input={"founder_id": str(f.id)},
            output={"verdict": "neutral"},
            evidence_ids=[str(uuid.uuid4())],
        )
        db.add_all([sh, memo, step])
        db.flush()

        assert (
            db.execute(
                select(func.count())
                .select_from(ScoreHistory)
                .where(ScoreHistory.founder_id == f.id)
            ).scalar_one()
            == 1
        )
        assert (
            db.execute(
                select(func.count()).select_from(Memo).where(Memo.opportunity_id == opp.id)
            ).scalar_one()
            == 1
        )
        assert (
            db.execute(
                select(func.count())
                .select_from(TraceStep)
                .where(TraceStep.opportunity_id == opp.id)
            ).scalar_one()
            == 1
        )

        # JSONB round-trips + forward relationships resolve.
        db.refresh(sh)
        db.refresh(memo)
        assert sh.components == {"tech": 0.4, "execution": 0.3}
        assert sh.founder.id == f.id
        assert memo.gaps == ["Cap table: not disclosed"]
        assert memo.quality == {"anchors_pass": True, "judge_mean": 0.85}
        assert memo.opportunity.id == opp.id
        assert step.evidence_ids and step.stage == "score_founder"
    finally:
        db.rollback()  # never persist test rows into the shared dev DB
        db.close()
