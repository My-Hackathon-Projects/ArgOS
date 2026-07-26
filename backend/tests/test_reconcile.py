"""Database-level contract for reconciliation of duplicate founder records."""

import uuid

from sqlalchemy import func, select

from app.db import SessionLocal
from app.entity_resolution import compact_person_name
from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    EntityMerge,
    Founder,
    FounderAlias,
    FounderCompany,
    FounderResolutionReview,
    Identity,
    Memo,
    Opportunity,
    ScoreHistory,
    Signal,
    ThreeAxis,
    TraceStep,
    founder_signal,
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
            kind="founder",
            external_id=f"signal-{suffix}",
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
        # Signal ownership lives solely in founder_signal now, not on the signal row.
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


def test_merge_keeps_every_distinct_handle_and_drops_the_shared_one() -> None:
    """The shared handle is *why* the two rows merge, so the merge must survive holding it twice.

    `identity` is unique per (founder, kind), so moving the duplicate's row across wholesale puts
    the same LinkedIn on the canonical founder twice and the merge aborts — on exactly the input
    that motivated it. Every value the canonical founder does not already have has to arrive.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        db.add_all([canonical, duplicate])
        db.flush()
        db.add_all(
            [
                Identity(founder_id=canonical.id, linkedin=f"ada-{suffix}", github=f"ada-{suffix}"),
                Identity(
                    founder_id=duplicate.id, linkedin=f"ada-{suffix}", twitter=f"ada{suffix[:8]}"
                ),
            ]
        )
        db.flush()

        merge_founders(
            db, canonical, duplicate, method="test", confidence=0.99, evidence={}, commit=False
        )
        db.flush()

        identities = (
            db.execute(select(Identity).where(Identity.founder_id == canonical.id)).scalars().all()
        )
        assert [i.linkedin for i in identities].count(f"ada-{suffix}") == 1
        assert {i.github for i in identities} >= {f"ada-{suffix}"}
        assert {i.twitter for i in identities} >= {f"ada{suffix[:8]}"}
    finally:
        db.rollback()
        db.close()


def test_merge_folds_two_deals_for_one_company_into_one_without_losing_the_screening() -> None:
    """One person and one venture is one deal — but the fund's work on both copies must survive.

    A duplicate founder row carries its own opportunity for the same company, and everything
    downstream of an opportunity (axes, memo, claims) is ondelete=CASCADE. Deleting the loser
    outright would silently take the screening with it, so its dependents move first.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        company = Company(name=f"Company {suffix}")
        db.add_all([canonical, duplicate, company])
        db.flush()
        kept = Opportunity(
            founder_id=canonical.id,
            company_id=company.id,
            company_name=f"Company {suffix}",
            status="screening",
        )
        folded = Opportunity(
            founder_id=duplicate.id,
            company_id=company.id,
            company_name=f"Company {suffix}",
            status="diligence",
            idea=f"Idea {suffix}",
        )
        db.add_all([kept, folded])
        db.flush()
        db.add_all(
            [
                ThreeAxis(opportunity_id=kept.id, axis="founder", verdict="bull", trend="stable"),
                ThreeAxis(opportunity_id=folded.id, axis="market", verdict="bear", trend="stable"),
                Memo(opportunity_id=folded.id, recommendation=f"Memo {suffix}"),
                Claim(
                    opportunity_id=folded.id,
                    category="achievement",
                    statement=f"Market claim {suffix}",
                ),
            ]
        )
        db.flush()

        merge_founders(
            db, canonical, duplicate, method="test", confidence=0.99, evidence={}, commit=False
        )
        db.flush()

        deals = (
            db.execute(select(Opportunity).where(Opportunity.founder_id == canonical.id))
            .scalars()
            .all()
        )
        assert len(deals) == 1
        survivor = deals[0]
        assert {axis.axis for axis in survivor.axes} == {"founder", "market"}
        assert (
            db.scalar(
                select(func.count()).select_from(Memo).where(Memo.opportunity_id == survivor.id)
            )
            == 1
        )
        assert (
            db.scalar(
                select(func.count()).select_from(Claim).where(Claim.opportunity_id == survivor.id)
            )
            == 1
        )
        # Neither copy's own fields are dropped: the idea only the folded row carried survives,
        # and the deal keeps the furthest stage either copy had reached.
        assert survivor.idea == f"Idea {suffix}"
        assert survivor.status == "diligence"
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
        signal = Signal(
            source="test",
            signal_type="profile",
            kind="founder",
            external_id=f"signal-{suffix}",
        )
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


def test_merge_keeps_evidence_cited_only_by_the_duplicate_claim() -> None:
    """Folding two copies of one claim must add the duplicate's citations, not destroy them.

    `Claim.evidence` cascades with delete-orphan, so reassigning `evidence.claim_id` in Python does
    not detach the row: the ORM still holds it in the deleted claim's collection and cascades it
    away. The existing conflict test never sees this — both its evidence rows cite the same signal,
    which takes the other branch. Evidence citing a signal the survivor lacks is the branch that
    loses data, and it loses the *stronger* row as readily as the weaker.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        db.add_all([canonical, duplicate])
        db.flush()
        signals = [
            Signal(
                source="test",
                signal_type="profile",
                kind="founder",
                external_id=f"signal-{index}-{suffix}",
            )
            for index in range(2)
        ]
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
        db.add_all([*signals, canonical_claim, duplicate_claim])
        db.flush()
        db.add_all(
            [
                ClaimEvidence(
                    claim_id=canonical_claim.id,
                    signal_id=signals[0].id,
                    stance="supports",
                    weight=0.4,
                ),
                ClaimEvidence(
                    claim_id=duplicate_claim.id,
                    signal_id=signals[1].id,
                    stance="supports",
                    weight=0.9,
                ),
            ]
        )
        db.flush()

        merge_founders(
            db, canonical, duplicate, method="test", confidence=0.99, evidence={}, commit=False
        )
        db.flush()
        db.expire_all()

        evidence = (
            db.execute(select(ClaimEvidence).where(ClaimEvidence.claim_id == canonical_claim.id))
            .scalars()
            .all()
        )
        assert {item.signal_id for item in evidence} == {signals[0].id, signals[1].id}
        assert {item.weight for item in evidence} == {0.4, 0.9}
    finally:
        db.rollback()
        db.close()


def test_merge_records_an_alias_for_the_duplicate_name_only_once() -> None:
    """The session runs autoflush=False, so a moved alias is invisible to the duplicate check.

    `merge_founders` then inserts a second alias with the same (founder_id, normalized_name) and
    `uq_founder_alias` rejects it. Because `reconcile_founders` commits once at the end, that one
    collision rolls back *every* merge in the run — and the run fails identically forever.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Ada Lovelace {suffix}")
        duplicate = Founder(display_name=f"Ada Byron {suffix}")
        db.add_all([canonical, duplicate])
        db.flush()
        db.add(
            FounderAlias(
                founder_id=duplicate.id,
                raw_name=duplicate.display_name or "",
                normalized_name=compact_person_name(duplicate.display_name),
                source="test",
            )
        )
        db.flush()

        merge_founders(
            db, canonical, duplicate, method="test", confidence=0.99, evidence={}, commit=False
        )
        db.flush()

        assert (
            db.scalar(
                select(func.count())
                .select_from(FounderAlias)
                .where(
                    FounderAlias.founder_id == canonical.id,
                    FounderAlias.normalized_name == compact_person_name(duplicate.display_name),
                )
            )
            == 1
        )
    finally:
        db.rollback()
        db.close()


def test_merge_keeps_the_record_of_why_the_two_were_held_apart() -> None:
    """A review row is the resolver's fork decision; merging the pair is its resolution.

    `founder_resolution_review.founder_id` is ondelete=CASCADE and `merge_founders` never moved it,
    so deleting the duplicate erased the evidence trail for the very question the merge answers.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canonical {suffix}")
        duplicate = Founder(display_name=f"Duplicate {suffix}")
        db.add_all([canonical, duplicate])
        db.flush()
        review = FounderResolutionReview(
            fingerprint=f"fingerprint-{suffix}",
            founder_id=duplicate.id,
            counterpart_founder_id=canonical.id,
            conflict_kinds="linkedin",
        )
        db.add(review)
        db.flush()
        review_id = review.id

        merge_founders(
            db, canonical, duplicate, method="test", confidence=0.99, evidence={}, commit=False
        )
        db.flush()
        db.expire_all()

        moved = db.get(FounderResolutionReview, review_id)
        assert moved is not None
        assert moved.founder_id == canonical.id
        assert moved.conflict_kinds == "linkedin"
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


def test_merge_preserves_attribution_provenance() -> None:
    """Merging must not null attribution metadata: claim trust weights are computed from it."""
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        canonical = Founder(display_name=f"Canon {suffix}")
        duplicate = Founder(display_name=f"Dupe {suffix}")
        signal = Signal(
            source="web",
            signal_type="profile",
            kind="founder",
            external_id=f"ext-{suffix}",
            canonical_url=f"https://example.test/{suffix}",
        )
        db.add_all([canonical, duplicate, signal])
        db.flush()
        db.execute(
            founder_signal.insert().values(
                founder_id=duplicate.id,
                signal_id=signal.id,
                attribution_confidence=0.9,
                attribution_method="exact_key",
            )
        )
        db.flush()

        merge_founders(
            db, canonical, duplicate, method="test", confidence=1.0, evidence={}, commit=False
        )

        row = db.execute(
            select(
                founder_signal.c.attribution_confidence,
                founder_signal.c.attribution_method,
            ).where(founder_signal.c.founder_id == canonical.id)
        ).one()
        assert row.attribution_confidence == 0.9
        assert row.attribution_method == "exact_key"
    finally:
        db.rollback()
        db.close()


def test_reconcile_does_not_merge_distinct_people_on_a_shared_org_handle():
    """The live case: openhelix-team was on 6 different researchers' profiles.

    reconcile compares pairs, so a pool-local view of "is this handle identifying?" sees one
    claimant per comparison and merges. The question has to be answered against the whole
    population, or a dry run proposes collapsing three distinct people into one.
    """
    db = SessionLocal()
    try:
        suffix = uuid.uuid4().hex
        org = f"openhelix-team-{suffix}"
        people = ["Xinyang Tong", "Pengxiang Ding", "Wenxuan Song"]
        for name in people:
            founder = Founder(display_name=f"{name} {suffix}", city="Munich")
            db.add(founder)
            db.flush()
            db.add(Identity(founder_id=founder.id, github=org))
        db.flush()

        result = reconcile_founders(db, dry_run=True)
        merged = [
            m
            for m in result.get("merges", [])
            if suffix in (m.get("left_name") or "") or suffix in (m.get("right_name") or "")
        ]
        assert not merged, f"proposed merging distinct people on an org handle: {merged}"
    finally:
        db.rollback()
        db.close()
