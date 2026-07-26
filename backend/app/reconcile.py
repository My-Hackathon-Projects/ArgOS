"""Safe, auditable reconciliation of duplicate founder rows."""

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
from app.models import (
    Claim,
    ClaimEvidence,
    EntityMerge,
    Founder,
    FounderAlias,
    FounderCompany,
    Identity,
    Opportunity,
    ScoreHistory,
    TraceStep,
    founder_signal,
)
from app.normalize import normalize_location


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
            else:
                evidence.claim_id = existing.id
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
    for table, column in (
        (Opportunity, Opportunity.founder_id),
        (ScoreHistory, ScoreHistory.founder_id),
        (TraceStep, TraceStep.founder_id),
    ):
        db.execute(update(table).where(column == duplicate.id).values({column.key: canonical.id}))
    db.execute(
        update(Identity).where(Identity.founder_id == duplicate.id).values(founder_id=canonical.id)
    )
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
            merged_founder_id=duplicate.id,
            merged_founder_ref=duplicate.id,
            method=method,
            confidence=confidence,
            evidence=evidence,
        )
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
    for founder in founders:
        raw_location = founder.raw_location or founder.city
        normalized = normalize_location(raw_location)
        if (
            founder.raw_location != normalized.raw_location
            or founder.city != normalized.city
            or founder.city_key != normalized.city_key
            or founder.country_code != normalized.country_code
            or founder.location_quality != normalized.quality
            or founder.city_geonameid != normalized.geonameid
        ):
            location_updates.append(
                {
                    "founder_id": str(founder.id),
                    "raw_location": normalized.raw_location,
                    "city": normalized.city,
                    "city_key": normalized.city_key,
                    "city_geonameid": normalized.geonameid,
                    "country_code": normalized.country_code,
                    "quality": normalized.quality,
                }
            )
            if not dry_run:
                founder.raw_location = normalized.raw_location
                founder.city = normalized.city
                founder.city_key = normalized.city_key
                founder.city_geonameid = normalized.geonameid
                founder.country_code = normalized.country_code
                founder.location_quality = normalized.quality
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
    return {
        "dry_run": dry_run,
        "location_update_count": len(location_updates),
        "merge_count": len(merges),
        "review_count": len(reviews),
        "location_updates": location_updates if dry_run else [],
        "merges": merges,
        "reviews": reviews,
    }
