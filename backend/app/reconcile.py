"""Safe, auditable reconciliation of duplicate founder rows."""

import logging
import uuid
from itertools import combinations

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from app.entity_resolution import (
    FounderCandidate,
    ResolutionResult,
    artifact_ids_by_founder,
    compact_person_name,
    has_shared_strong_identity,
    non_identifying_handles,
    resolve_candidates,
)
from app.identity import ALL_KINDS
from app.models import (
    Claim,
    ClaimEvidence,
    EntityMerge,
    Founder,
    FounderAlias,
    FounderCompany,
    FounderResolutionReview,
    Identity,
    Memo,
    Opportunity,
    ScoreHistory,
    ThreeAxis,
    TraceStep,
    founder_signal,
)
from app.places import apply_location, institution_country_index

log = logging.getLogger(__name__)


def _candidate(
    founder: Founder, artifacts: dict[str, tuple[str, ...]] | None = None
) -> FounderCandidate:
    def identity_values(field: str) -> tuple[str, ...] | None:
        values = tuple(
            value
            for identity in founder.identities
            if (value := getattr(identity, field)) is not None
        )
        return values or None

    return FounderCandidate(
        founder_id=str(founder.id),
        display_name=founder.display_name,
        city=founder.city or founder.raw_location,
        current_company=founder.current_company,
        artifact_ids=(artifacts or {}).get(str(founder.id), ()),
        github=identity_values("github"),
        linkedin=identity_values("linkedin"),
        twitter=identity_values("twitter"),
        orcid=identity_values("orcid"),
        website=identity_values("website"),
        education=tuple(str(x) for x in (founder.education or [])),
    )


def find_merge_candidates(db: Session) -> list[tuple[Founder, Founder, ResolutionResult]]:
    founders = (
        db.execute(
            select(Founder)
            .options(selectinload(Founder.identities))
            .order_by(Founder.first_discovered_at.nullsfirst(), Founder.id)
        )
        .scalars()
        .all()
    )
    results: list[tuple[Founder, Founder, ResolutionResult]] = []
    # Fetched once for the whole sweep, not per pair: this is O(N^2) over founders already.
    artifacts = artifact_ids_by_founder(db)
    candidates = {str(founder.id): _candidate(founder, artifacts) for founder in founders}
    # Computed over EVERY founder, not per pair: a pairwise view sees one claimant per
    # comparison and would merge distinct people on a shared organisation account
    # (openhelix-team sat on six different researchers).
    non_identifying = non_identifying_handles(list(candidates.values()))
    for left, right in combinations(founders, 2):
        left_candidate = candidates[str(left.id)]
        right_candidate = candidates[str(right.id)]
        # Candidate generation is deliberately broad enough for middle-name and abbreviation
        # variants, but not every pair needs the full evidence comparison.
        same_name = compact_person_name(left.display_name) == compact_person_name(
            right.display_name
        )
        shared_identity = has_shared_strong_identity(left_candidate, right_candidate)
        if not same_name and not shared_identity:
            continue
        result = resolve_candidates(
            left_candidate, [right_candidate], non_identifying=non_identifying
        )
        if result.decision in {"merge", "review"}:
            results.append((left, right, result))
    return results


def _move_claims(db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID) -> None:
    canonical_claims = {
        claim.dedup_key: claim
        for claim in db.execute(select(Claim).where(Claim.founder_id == canonical_id)).scalars()
        if claim.dedup_key
    }
    duplicate_claims = (
        db.execute(select(Claim).where(Claim.founder_id == duplicate_id)).scalars().all()
    )
    for claim in duplicate_claims:
        existing = canonical_claims.get(claim.dedup_key) if claim.dedup_key else None
        if existing is None:
            claim.founder_id = canonical_id
            continue
        existing_evidence = {
            evidence.signal_id: evidence
            for evidence in db.execute(
                select(ClaimEvidence).where(ClaimEvidence.claim_id == existing.id)
            ).scalars()
        }
        for evidence in list(claim.evidence):
            matching_evidence = existing_evidence.get(evidence.signal_id)
            if matching_evidence is not None:
                # The schema allows one stance per claim/signal. A refutation must win over a
                # supporting duplicate; otherwise a contradiction would disappear on merge.
                if matching_evidence.stance != evidence.stance:
                    matching_evidence.stance = "refutes"
                    rationales = filter(None, (matching_evidence.rationale, evidence.rationale))
                    matching_evidence.rationale = " | ".join(dict.fromkeys(rationales)) or None
                    matching_evidence.weight = max(
                        matching_evidence.weight or 0.0, evidence.weight or 0.0
                    )
                    matching_evidence.extraction_conf = max(
                        matching_evidence.extraction_conf or 0.0,
                        evidence.extraction_conf or 0.0,
                    )
                db.delete(evidence)
        # Reassigning `evidence.claim_id` in Python does NOT move the row: the relationship is
        # cascade="all, delete-orphan", so the ORM still holds these objects in the deleted claim's
        # collection and cascades them away on flush — destroying the citations the merge exists to
        # combine, the strongest as readily as the weakest. Move them in SQL, then expire the
        # collection so the cascade reloads it (now empty) instead of trusting a stale copy. Same
        # trap, same fix as the founder delete below.
        db.flush()
        db.execute(
            update(ClaimEvidence)
            .where(ClaimEvidence.claim_id == claim.id)
            .values(claim_id=existing.id)
            .execution_options(synchronize_session=False)
        )
        db.expire(claim, ["evidence"])
        db.delete(claim)


def _move_founder_companies(db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID) -> None:
    canonical_company_ids = {
        company_id
        for (company_id,) in db.execute(
            select(FounderCompany.company_id).where(FounderCompany.founder_id == canonical_id)
        )
    }
    duplicate_links = db.execute(
        select(FounderCompany).where(FounderCompany.founder_id == duplicate_id)
    ).scalars()
    for link in duplicate_links:
        if link.company_id in canonical_company_ids:
            db.delete(link)
        else:
            link.founder_id = canonical_id


def _move_identities(db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID) -> None:
    """Carry over every handle the canonical founder does not already hold, and only those.

    The shared handle is usually *why* the two rows are being merged, so moving the duplicate's
    identity row across wholesale puts one value on the canonical founder twice and
    `uq_identity_founder_<kind>` rejects it — the merge fails on exactly the input that motivated
    it. Values are canonical tokens (`app.identity`), so equality here is identity, not spelling.
    A row emptied of everything it carried is dropped rather than left as a founder-shaped blank.
    """
    held: dict[str, set[str]] = {kind: set() for kind in ALL_KINDS}
    for identity in db.execute(
        select(Identity).where(Identity.founder_id == canonical_id)
    ).scalars():
        for kind in ALL_KINDS:
            if (value := getattr(identity, kind)) is not None:
                held[kind].add(value)
    duplicate_identities = (
        db.execute(select(Identity).where(Identity.founder_id == duplicate_id)).scalars().all()
    )
    for identity in duplicate_identities:
        for kind in ALL_KINDS:
            value = getattr(identity, kind)
            if value is None:
                continue
            if value in held[kind]:
                setattr(identity, kind, None)
            else:
                held[kind].add(value)
        carries_anything = any(
            getattr(identity, field) is not None for field in (*ALL_KINDS, "email", "other_socials")
        )
        if carries_anything:
            identity.founder_id = canonical_id
        else:
            db.delete(identity)


_STATUS_RANK = {"screening": 0, "diligence": 1, "rejected": 2, "decided": 2}
"""How far a deal has got. A recorded outcome outranks an in-flight stage; the two outcomes are
deliberately equal, because inventing a precedence between `rejected` and `decided` would let a
merge overwrite a real verdict with the other copy's."""


def _fold_opportunity(db: Session, survivor: Opportunity, loser: Opportunity) -> None:
    """Combine two deals for one (founder, company), keeping the fund's work on both."""
    existing_axes = {axis.axis for axis in survivor.axes}
    for axis in db.execute(select(ThreeAxis).where(ThreeAxis.opportunity_id == loser.id)).scalars():
        # uq_three_axis_opportunity_axis allows one row per axis. The survivor's verdict stands;
        # the axes it was never scored on come across.
        if axis.axis in existing_axes:
            db.delete(axis)
        else:
            axis.opportunity_id = survivor.id
            existing_axes.add(axis.axis)
    db.flush()
    for table, column in (
        (Memo, Memo.opportunity_id),
        (Claim, Claim.opportunity_id),
        (TraceStep, TraceStep.opportunity_id),
    ):
        db.execute(
            update(table)
            .where(column == loser.id)
            .values({column.key: survivor.id})
            .execution_options(synchronize_session=False)
        )
    for field in ("company_name", "idea", "sector", "geo", "source", "decision", "decided_at"):
        if getattr(survivor, field) is None:
            setattr(survivor, field, getattr(loser, field))
    if _STATUS_RANK[loser.status] > _STATUS_RANK[survivor.status]:
        survivor.status = loser.status
    # Provenance stays truthful: the deal is as old as the earliest copy of it.
    for field in ("first_signal_at", "created_at"):
        loser_value, survivor_value = getattr(loser, field), getattr(survivor, field)
        if loser_value is not None and (survivor_value is None or loser_value < survivor_value):
            setattr(survivor, field, loser_value)
    db.flush()
    # Core delete: an ORM delete would run relationship synchronization over the collections just
    # moved and null their opportunity_id back out. Dependents are already on the survivor, so the
    # database-level CASCADE has nothing left to take.
    db.execute(
        delete(Opportunity)
        .where(Opportunity.id == loser.id)
        .execution_options(synchronize_session=False)
    )
    db.expunge(loser)
    # The rows above moved in SQL, so the survivor's loaded collections predate them.
    db.expire(survivor, ["axes", "claims"])


def _move_opportunities(db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID) -> None:
    """One person and one venture is one deal (`uq_opportunity_founder_company`).

    A blind `UPDATE opportunity SET founder_id` produced a second deal for the pair whenever both
    founder rows had been screened against the same company. Deleting the loser outright is not an
    option either: `three_axis`, `memo`, `claim` and `trace_step` all hang off an opportunity with
    ondelete=CASCADE, so it would take the screening with it.
    """
    canonical_deals = {
        deal.company_id: deal
        for deal in db.execute(
            select(Opportunity).where(Opportunity.founder_id == canonical_id)
        ).scalars()
        if deal.company_id is not None
    }
    duplicate_deals = (
        db.execute(select(Opportunity).where(Opportunity.founder_id == duplicate_id))
        .scalars()
        .all()
    )
    for deal in duplicate_deals:
        # A company-less idea-stage deal is outside the unique index and always moves.
        survivor = canonical_deals.get(deal.company_id) if deal.company_id is not None else None
        if survivor is None:
            deal.founder_id = canonical_id
            if deal.company_id is not None:
                canonical_deals[deal.company_id] = deal
        else:
            _fold_opportunity(db, survivor, deal)


def _move_aliases(db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID) -> None:
    canonical_names = {
        normalized_name
        for (normalized_name,) in db.execute(
            select(FounderAlias.normalized_name).where(FounderAlias.founder_id == canonical_id)
        )
    }
    duplicate_aliases = db.execute(
        select(FounderAlias).where(FounderAlias.founder_id == duplicate_id)
    ).scalars()
    for alias in duplicate_aliases:
        if alias.normalized_name in canonical_names:
            db.delete(alias)
        else:
            alias.founder_id = canonical_id
            canonical_names.add(alias.normalized_name)


def _move_signal_attributions(
    db: Session, canonical_id: uuid.UUID, duplicate_id: uuid.UUID
) -> None:
    """Preserve every artifact link AND its provenance when two founders are merged.

    Carrying only (founder_id, signal_id) silently nulled attribution_confidence and
    attribution_method. Claim trust weights read that confidence
    (app.claims.service._add_evidence) and fall back to the legacy single-owner
    signal.resolution_confidence, which the current write path never sets — so merging a
    founder degraded the trust score of every claim built on the moved evidence. Keep the
    earliest attribution timestamp and the strongest confidence.
    """
    rows = db.execute(
        select(
            founder_signal.c.signal_id,
            founder_signal.c.attribution_confidence,
            founder_signal.c.attribution_method,
            founder_signal.c.attributed_at,
        ).where(founder_signal.c.founder_id == duplicate_id)
    ).all()
    for signal_id, confidence, method, attributed_at in rows:
        statement = insert(founder_signal).values(
            founder_id=canonical_id,
            signal_id=signal_id,
            attribution_confidence=confidence,
            attribution_method=method,
            attributed_at=attributed_at,
        )
        db.execute(
            statement.on_conflict_do_update(
                index_elements=["founder_id", "signal_id"],
                set_={
                    "attribution_confidence": func.greatest(
                        func.coalesce(founder_signal.c.attribution_confidence, 0.0),
                        func.coalesce(statement.excluded.attribution_confidence, 0.0),
                    ),
                    "attribution_method": func.coalesce(
                        founder_signal.c.attribution_method,
                        statement.excluded.attribution_method,
                    ),
                    "attributed_at": func.least(
                        founder_signal.c.attributed_at, statement.excluded.attributed_at
                    ),
                },
            )
        )
    db.execute(delete(founder_signal).where(founder_signal.c.founder_id == duplicate_id))


def merge_founders(
    db: Session,
    canonical: Founder,
    duplicate: Founder,
    *,
    method: str,
    confidence: float,
    evidence: dict,
    commit: bool = True,
) -> None:
    """Move all founder-owned records to canonical and retain an audit trail."""
    if canonical.id == duplicate.id:
        return
    _move_claims(db, canonical.id, duplicate.id)
    _move_founder_companies(db, canonical.id, duplicate.id)
    _move_aliases(db, canonical.id, duplicate.id)
    _move_signal_attributions(db, canonical.id, duplicate.id)
    _move_identities(db, canonical.id, duplicate.id)
    _move_opportunities(db, canonical.id, duplicate.id)
    for table, column in (
        (ScoreHistory, ScoreHistory.founder_id),
        (TraceStep, TraceStep.founder_id),
        # The record of why these two were ever held apart survives the merge that answers it.
        # founder_id is ondelete=CASCADE, so leaving it behind deleted the review outright.
        (FounderResolutionReview, FounderResolutionReview.founder_id),
        (FounderResolutionReview, FounderResolutionReview.counterpart_founder_id),
    ):
        db.execute(update(table).where(column == duplicate.id).values({column.key: canonical.id}))
    # A review naming the merged pair now names one founder twice, which is no longer a conflict
    # to review — it is a resolved one, and the merge itself is the audit record.
    db.execute(
        update(FounderResolutionReview)
        .where(FounderResolutionReview.counterpart_founder_id == canonical.id)
        .where(FounderResolutionReview.founder_id == canonical.id)
        .values(counterpart_founder_id=None)
    )
    # The alias moves above are still pending in the session, and it runs autoflush=False — so the
    # existence check below would query the database, miss them, and insert a duplicate that
    # `uq_founder_alias` rejects. One collision rolls back every merge in the run, forever.
    db.flush()
    duplicate_name = compact_person_name(duplicate.display_name)
    alias_exists = db.scalar(
        select(FounderAlias.id).where(
            FounderAlias.founder_id == canonical.id,
            FounderAlias.normalized_name == duplicate_name,
        )
    )
    if duplicate_name and alias_exists is None:
        db.add(
            FounderAlias(
                founder_id=canonical.id,
                raw_name=duplicate.display_name or "",
                normalized_name=duplicate_name,
                source="reconciliation",
            )
        )
    db.add(
        EntityMerge(
            canonical_founder_id=canonical.id,
            canonical_founder_ref=canonical.id,
            merged_founder_id=duplicate.id,
            merged_founder_ref=duplicate.id,
            method=method,
            confidence=confidence,
            evidence=evidence,
        )
    )
    # A person's row is about to be deleted and their whole history reattributed. `entity_merge`
    # records it in the database; this records it where an operator watching the cron will see it.
    log.info(
        "merge: %s (%s) <- %s (%s) via %s conf=%.2f evidence=%s",
        canonical.display_name,
        canonical.id,
        duplicate.display_name,
        duplicate.id,
        method,
        confidence,
        evidence,
    )
    # Flush all FK moves before deleting the duplicate. Using a SQL delete avoids SQLAlchemy
    # relationship synchronization setting moved claims back to NULL.
    db.flush()
    db.execute(
        delete(Founder)
        .where(Founder.id == duplicate.id)
        .execution_options(synchronize_session=False)
    )
    if commit:
        db.commit()


def reconcile_founders(db: Session, *, dry_run: bool = True) -> dict:
    founders = db.execute(select(Founder)).scalars().all()
    location_updates = []
    # One index for the sweep instead of a query per founder.
    institutions = institution_country_index(db)
    _PLACE_COLUMNS = ("city", "city_key", "city_geonameid", "country_code", "location_quality")
    for founder in founders:
        before = {column: getattr(founder, column) for column in _PLACE_COLUMNS}
        # Written through the single writer even in a dry run, then rolled back below — there is
        # no second implementation of the rule to drift from what a real run would do.
        apply_location(db, founder, institutions=institutions)
        after = {column: getattr(founder, column) for column in _PLACE_COLUMNS}
        if before == after:
            continue
        location_updates.append(
            {
                "founder_id": str(founder.id),
                "display_name": founder.display_name,
                "raw_location": founder.raw_location,
                # Both sides: a sweep that rewrites every founder's location and reports only the
                # new value gives an operator no way to see what it destroyed.
                "before": {
                    key: str(value) if value is not None else None for key, value in before.items()
                },
                "after": {
                    key: str(value) if value is not None else None for key, value in after.items()
                },
            }
        )
        if dry_run:
            for column, value in before.items():
                setattr(founder, column, value)
    log.info(
        "reconcile: %d/%d founders change location%s",
        len(location_updates),
        len(founders),
        " (dry run)" if dry_run else "",
    )
    merges = []
    reviews = []

    def item_for(left: Founder, right: Founder, result: ResolutionResult) -> dict:
        return {
            "left_id": str(left.id),
            "left_name": left.display_name,
            "right_id": str(right.id),
            "right_name": right.display_name,
            "decision": result.decision,
            "confidence": result.confidence,
            "reasons": list(result.reasons),
            "conflicts": list(result.conflicts),
        }

    if dry_run:
        candidates = find_merge_candidates(db)
        for left, right, result in candidates:
            item = item_for(left, right, result)
            if result.decision == "merge":
                merges.append(item)
            else:
                reviews.append(item)
    else:
        # Merge one current pair at a time. Rebuilding candidates after each deletion prevents
        # stale overlapping pairs in a three-founder cluster from referencing removed rows.
        while True:
            merge_candidate = next(
                (
                    candidate
                    for candidate in find_merge_candidates(db)
                    if candidate[2].decision == "merge"
                ),
                None,
            )
            if merge_candidate is None:
                break
            left, right, result = merge_candidate
            merges.append(item_for(left, right, result))
            merge_founders(
                db,
                left,
                right,
                method="automatic_evidence",
                confidence=result.confidence,
                evidence=result.evidence,
                commit=False,
            )
        for left, right, result in find_merge_candidates(db):
            if result.decision == "review":
                reviews.append(item_for(left, right, result))
    if not dry_run:
        db.commit()
    log.info(
        "reconcile: %d merges, %d reviews over %d founders%s",
        len(merges),
        len(reviews),
        len(founders),
        " (dry run)" if dry_run else "",
    )
    return {
        "dry_run": dry_run,
        "location_update_count": len(location_updates),
        "merge_count": len(merges),
        "review_count": len(reviews),
        # Reported in BOTH modes. Returning them only in the dry run meant the run that actually
        # rewrote every founder's place was the one that reported nothing.
        "location_updates": location_updates,
        "merges": merges,
        "reviews": reviews,
    }
