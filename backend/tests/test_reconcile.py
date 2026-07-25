"""Database-level contract for reconciliation of duplicate founder records."""

import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    EntityMerge,
    Founder,
    FounderAlias,
    FounderCompany,
    Identity,
    Opportunity,
    ScoreHistory,
    Signal,
    TraceStep,
)
from app.reconcile import merge_founders, reconcile_founders


def test_merge_moves_founder_owned_records_and_keeps_deleted_uuid_in_audit() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        company = Company(name=f"Company {suffix}")
        db.add_all([canonical, duplicate, company])
        db.flush()

        identity = Identity(founder_id=duplicate.id, linkedin=f"https://linkedin.com/in/{suffix}")
        signal = Signal(
            source="test",
            signal_type="profile",
            external_id=f"signal-{suffix}",
            founder_id=duplicate.id,
        )
        duplicate.signals.append(signal)
        claim = Claim(
            founder_id=duplicate.id,
            category="achievement",
            statement=f"Claim {suffix}",
        )
        opportunity = Opportunity(founder_id=duplicate.id, idea=f"Idea {suffix}")
        score_history = ScoreHistory(founder_id=duplicate.id, score=42.0)
        trace_step = TraceStep(founder_id=duplicate.id, stage="score_founder")
        founder_company = FounderCompany(founder_id=duplicate.id, company_id=company.id)
        alias = FounderAlias(
            founder_id=duplicate.id,
            raw_name=f"D. {suffix}",
            normalized_name=f"d {suffix}",
            source="test",
        )
        db.add_all(
            [
                identity,
                signal,
                claim,
                opportunity,
                score_history,
                trace_step,
                founder_company,
                alias,
            ]
        )
        db.flush()

        duplicate_id = duplicate.id
        merge_founders(
            db,
            canonical,
            duplicate,
            method="test",
            confidence=0.99,
            evidence={"linkedin": "shared"},
            commit=False,
        )
        db.expire_all()

        assert db.get(Founder, duplicate_id) is None
        moved_identity = db.get(Identity, identity.id)
        moved_signal = db.get(Signal, signal.id)
        moved_claim = db.get(Claim, claim.id)
        moved_opportunity = db.get(Opportunity, opportunity.id)
        moved_score_history = db.get(ScoreHistory, score_history.id)
        moved_trace_step = db.get(TraceStep, trace_step.id)
        moved_founder_company = db.get(FounderCompany, founder_company.id)
        moved_alias = db.get(FounderAlias, alias.id)
        assert moved_identity is not None
        assert moved_signal is not None
        assert moved_claim is not None
        assert moved_opportunity is not None
        assert moved_score_history is not None
        assert moved_trace_step is not None
        assert moved_founder_company is not None
        assert moved_alias is not None
        assert moved_identity.founder_id == canonical.id
        assert moved_signal.founder_id == canonical.id
        assert moved_signal.id in {item.id for item in canonical.signals}
        assert moved_claim.founder_id == canonical.id
        assert moved_opportunity.founder_id == canonical.id
        assert moved_score_history.founder_id == canonical.id
        assert moved_trace_step.founder_id == canonical.id
        assert moved_founder_company.founder_id == canonical.id
        assert moved_alias.founder_id == canonical.id

        audit = db.execute(
            select(EntityMerge).where(EntityMerge.canonical_founder_id == canonical.id)
        ).scalar_one()
        assert audit.merged_founder_id is None
        assert audit.merged_founder_ref == duplicate_id
    finally:
        db.rollback()
        db.close()


def test_merge_deduplicates_company_links_and_aliases() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        company = Company(name=f"Company {suffix}")
        db.add_all([canonical, duplicate, company])
        db.flush()
        duplicate_name = f"duplicate {suffix}"
        db.add_all(
            [
                FounderCompany(founder_id=canonical.id, company_id=company.id),
                FounderCompany(founder_id=duplicate.id, company_id=company.id),
                FounderAlias(
                    founder_id=canonical.id,
                    raw_name=duplicate.display_name or "",
                    normalized_name=duplicate_name,
                    source="test",
                ),
                FounderAlias(
                    founder_id=duplicate.id,
                    raw_name=duplicate.display_name or "",
                    normalized_name=duplicate_name,
                    source="test",
                ),
            ]
        )
        db.flush()

        merge_founders(
            db,
            canonical,
            duplicate,
            method="test",
            confidence=0.99,
            evidence={},
            commit=False,
        )
        db.flush()

        assert (
            db.scalar(
                select(func.count())
                .select_from(FounderCompany)
                .where(FounderCompany.founder_id == canonical.id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count())
                .select_from(FounderAlias)
                .where(
                    FounderAlias.founder_id == canonical.id,
                    FounderAlias.normalized_name == duplicate_name,
                )
            )
            == 1
        )
    finally:
        db.rollback()
        db.close()


def test_merge_keeps_a_refutation_when_duplicate_claim_evidence_conflicts() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        db.add_all([canonical, duplicate])
        db.flush()
        signal = Signal(source="test", signal_type="profile", external_id=f"signal-{suffix}")
        canonical_claim = Claim(
            founder_id=canonical.id,
            category="achievement",
            statement=f"Claim {suffix}",
            dedup_key=f"claim-{suffix}",
        )
        duplicate_claim = Claim(
            founder_id=duplicate.id,
            category="achievement",
            statement=f"Claim {suffix}",
            dedup_key=f"claim-{suffix}",
        )
        db.add_all([signal, canonical_claim, duplicate_claim])
        db.flush()
        db.add_all(
            [
                ClaimEvidence(
                    claim_id=canonical_claim.id,
                    signal_id=signal.id,
                    stance="supports",
                    rationale="supports fixture",
                ),
                ClaimEvidence(
                    claim_id=duplicate_claim.id,
                    signal_id=signal.id,
                    stance="refutes",
                    rationale="refutes fixture",
                ),
            ]
        )
        db.flush()

        merge_founders(
            db,
            canonical,
            duplicate,
            method="test",
            confidence=0.99,
            evidence={},
            commit=False,
        )
        db.flush()

        evidence = db.execute(
            select(ClaimEvidence).where(ClaimEvidence.claim_id == canonical_claim.id)
        ).scalar_one()
        assert evidence.stance == "refutes"
        assert evidence.rationale is not None
        assert "supports fixture" in evidence.rationale
        assert "refutes fixture" in evidence.rationale
    finally:
        db.rollback()
        db.close()


def test_reconciliation_rebuilds_candidates_after_each_merge_in_a_cluster() -> None:
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        founders = [Founder(display_name="Ada Lovelace") for _ in range(3)]
        db.add_all(founders)
        db.flush()
        founder_ids = [founder.id for founder in founders]
        db.add_all(
            [
                Identity(founder_id=founder.id, linkedin=f"linkedin.com/in/ada-{suffix}")
                for founder in founders
            ]
        )
        db.flush()

        result = reconcile_founders(db, dry_run=False)
        assert result["merge_count"] >= 2
        db.expire_all()
        assert sum(db.get(Founder, founder_id) is not None for founder_id in founder_ids) == 1
    finally:
        db.rollback()
        db.close()
