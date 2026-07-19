"""Claim generation: cold build + warm update, single-writer persist, Founder Score recompute.

Event-driven — called for the founders a discovery run just touched (sourcing.service tail-call);
warm-update skip on `last_claimed_at` makes that effectively "touched founders only". Also runnable
standalone (app.claims.run) over every founder with signals since their last_claimed_at.

Cold build (founder has no claims): one LLM pass over ALL signals -> deduplicated claims.
Warm update (has claims): only signals since last_claimed_at -> match-or-mint against existing.
Trust + Founder Score are deterministic recomputes over what was written.
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims import extract, score
from app.claims import trust as trust_mod
from app.claims.schemas import CATEGORIES
from app.db import SessionLocal
from app.models import Claim, ClaimEvidence, Founder, JobRun, Signal

_RELEVANCE = 0.85  # v1: fixed per-evidence relevance (the LLM asserted the link); refine later.


def _iso(dt: datetime | None) -> str | None:
    return dt.isoformat() if dt else None


def _sig(s: Signal) -> dict:
    return {
        "source": s.source,
        "signal_type": s.signal_type,
        "title": s.title,
        "summary": s.summary,
        "canonical_url": s.canonical_url,
        "occurred_at": _iso(s.occurred_at),
    }


def _founder_dict(f: Founder) -> dict:
    return {
        "display_name": f.display_name,
        "occupation": f.occupation,
        "current_company": f.current_company,
    }


def _max_occurred(signals: list[Signal], idxs: list[int]) -> datetime | None:
    dates = [
        signals[i].occurred_at for i in idxs if 0 <= i < len(signals) and signals[i].occurred_at
    ]
    return max(dates) if dates else None


def _add_evidence(db: Session, claim_id, signal: Signal, stance: str, seen: set) -> bool:
    key = (claim_id, signal.id)
    if key in seen:  # idempotent: never violate uq_claim_evidence_edge
        return False
    seen.add(key)
    db.add(
        ClaimEvidence(
            claim_id=claim_id,
            signal_id=signal.id,
            stance=stance,
            weight=trust_mod.evidence_weight(
                signal.source_reliability, signal.resolution_confidence, _RELEVANCE
            ),
            extraction_conf=_RELEVANCE,
        )
    )
    return True


def _mint(
    db: Session, founder_id, ec, signals: list[Signal], seen: set, used_keys: set
) -> Claim | None:
    sup = [i for i in ec.supporting_signals if 0 <= i < len(signals)]
    if not sup:
        return None  # no citation -> reject (anti-hallucination guardrail)
    attrs = dict(ec.attributes or {})
    attrs["impact"] = ec.impact
    attrs["occurred_at"] = _iso(_max_occurred(signals, sup))
    # A page URL evidences many facts; if the LLM reuses one as a key, it's not per-fact -> drop it.
    key = ec.dedup_key
    if key and key in used_keys:
        key = None
    if key:
        used_keys.add(key)
    claim = Claim(
        founder_id=founder_id,
        category=ec.category,
        statement=ec.statement,
        attributes=attrs,
        dedup_key=key,
        status="unverified",
    )
    db.add(claim)
    db.flush()
    for i in sup:
        _add_evidence(db, claim.id, signals[i], "supports", seen)
    for i in ec.refuting_signals:
        if 0 <= i < len(signals):
            _add_evidence(db, claim.id, signals[i], "refutes", seen)
    return claim


def _recompute_trust(db: Session, claim: Claim) -> None:
    rows = db.execute(
        select(ClaimEvidence, Signal.source)
        .join(Signal, ClaimEvidence.signal_id == Signal.id)
        .where(ClaimEvidence.claim_id == claim.id)
    ).all()
    supports = [e.weight for e, _ in rows if e.stance == "supports" and e.weight is not None]
    refutes = [e.weight for e, _ in rows if e.stance == "refutes" and e.weight is not None]
    sources = sorted({src for _, src in rows})
    claim.trust_score = trust_mod.trust_score(supports, refutes)
    claim.status = trust_mod.derive_status(claim.trust_score, refutes)
    claim.trust_components = trust_mod.trust_components(supports, refutes, sources)


def _recompute_founder_score(db: Session, founder: Founder) -> None:
    claims = db.execute(select(Claim).where(Claim.founder_id == founder.id)).scalars().all()
    rows = []
    for c in claims:
        attrs = c.attributes or {}
        occ = attrs.get("occurred_at")
        rows.append(
            {
                "trust": c.trust_score,
                "impact": attrs.get("impact", 0.5),
                "category": c.category,
                "occurred_at": datetime.fromisoformat(occ) if occ else None,
            }
        )
    founder.founder_score, founder.components = score.founder_score(rows)


def run_claims_for_founder(db: Session, founder_id) -> dict:
    founder = db.get(Founder, founder_id)
    if founder is None:
        raise ValueError(f"founder {founder_id} not found")
    all_signals = (
        db.execute(
            select(Signal).where(Signal.founder_id == founder_id).order_by(Signal.occurred_at)
        )
        .scalars()
        .all()
    )
    if not all_signals:
        return {"founder_id": str(founder_id), "skipped": "no signals"}

    existing = db.execute(select(Claim).where(Claim.founder_id == founder_id)).scalars().all()
    seen: set = set()
    used_keys: set = {c.dedup_key for c in existing if c.dedup_key}
    minted = 0
    attached = 0
    touched: set = set()

    def _valid(ec) -> bool:
        return ec.category in CATEGORIES and bool(ec.statement.strip())

    if not existing:
        # COLD BUILD — one pass over all signals.
        result = extract.extract_claims(
            _founder_dict(founder), [_sig(s) for s in all_signals], smart=True
        )
        for ec in result.claims:
            if not _valid(ec):
                continue
            claim = _mint(db, founder_id, ec, all_signals, seen, used_keys)
            if claim:
                minted += 1
                touched.add(claim.id)
    else:
        # WARM UPDATE — only new signals since last_claimed_at.
        cutoff = founder.last_claimed_at
        new_signals = [
            s for s in all_signals if cutoff is None or (s.ingested_at and s.ingested_at > cutoff)
        ]
        if not new_signals:
            founder.last_claimed_at = datetime.now(UTC)
            db.commit()
            return {"founder_id": str(founder_id), "skipped": "no new signals"}
        # preload existing edges so re-adjudication can't violate the unique edge constraint
        for cid, sid in db.execute(
            select(ClaimEvidence.claim_id, ClaimEvidence.signal_id)
            .join(Claim, ClaimEvidence.claim_id == Claim.id)
            .where(Claim.founder_id == founder_id)
        ).all():
            seen.add((cid, sid))
        by_cat: dict[str, list[Claim]] = {}
        for c in existing:
            by_cat.setdefault(c.category, []).append(c)
        dedup_index = {c.dedup_key: c for c in existing if c.dedup_key}

        result = extract.extract_claims(
            _founder_dict(founder), [_sig(s) for s in new_signals], smart=True
        )
        for ec in result.claims:
            if not _valid(ec):
                continue
            target = dedup_index.get(ec.dedup_key) if ec.dedup_key else None
            stance = "supports"
            if target is None:
                cands = by_cat.get(ec.category, [])
                if cands:
                    d = extract.adjudicate(
                        {"statement": ec.statement, "category": ec.category},
                        [{"statement": c.statement} for c in cands],
                        smart=False,
                    )
                    if (
                        d.action == "attach"
                        and d.existing_index is not None
                        and 0 <= d.existing_index < len(cands)
                    ):
                        target = cands[d.existing_index]
                        stance = "refutes" if d.stance == "refutes" else "supports"
            if target is not None:
                for i in ec.supporting_signals:
                    if 0 <= i < len(new_signals) and _add_evidence(
                        db, target.id, new_signals[i], stance, seen
                    ):
                        attached += 1
                        touched.add(target.id)
            else:
                claim = _mint(db, founder_id, ec, new_signals, seen, used_keys)
                if claim:
                    minted += 1
                    touched.add(claim.id)

    db.flush()
    for cid in touched:
        _recompute_trust(db, db.get(Claim, cid))
    before = founder.founder_score
    _recompute_founder_score(db, founder)
    founder.last_claimed_at = datetime.now(UTC)
    db.commit()
    return {
        "founder_id": str(founder_id),
        "founder": founder.display_name,
        "mode": "cold" if not existing else "warm",
        "claims_minted": minted,
        "evidence_attached": attached,
        "founder_score": {"before": before, "after": founder.founder_score},
        "components": founder.components,
    }


def pending_founder_ids(db: Session) -> list:
    """Founders with a signal newer than their last_claimed_at (or never claimed).

    Set-based: one indexed query returns exactly the founders that need (re)claiming, so a run is
    O(founders-with-new-signals), never O(all-founders). This is the scalability guard — untouched
    founders are never loaded, extracted, or even iterated.
    """
    return (
        db.execute(
            select(Signal.founder_id)
            .join(Founder, Founder.id == Signal.founder_id)
            .where(
                Signal.founder_id.isnot(None),
                (Founder.last_claimed_at.is_(None))
                | (Signal.ingested_at > Founder.last_claimed_at),
            )
            .distinct()
        )
        .scalars()
        .all()
    )


def run_claims(db: Session, founder_ids: list | None = None) -> dict:
    """Generate claims for founders with NEW signals only.

    founder_ids: explicit set (e.g. the founders a discovery run just touched). If None, resolve it
    via pending_founder_ids() — so nothing runs for founders whose signals didn't change.
    """
    job = JobRun(source="claims")
    db.add(job)
    db.flush()
    if founder_ids is None:
        founder_ids = pending_founder_ids(db)
    results = [run_claims_for_founder(db, fid) for fid in founder_ids]
    job.finished_at = datetime.now(UTC)
    job.new_signals = sum(r.get("claims_minted", 0) for r in results)
    db.commit()
    return {"founders_processed": len(founder_ids), "results": results, "job_run_id": str(job.id)}


def claims_job() -> dict:
    """Cron callable: claim generation for founders with new signals (opens its own session).

    Scheduled decoupled from sourcing (see app.scheduler): sourcing absorbs signals, this picks up
    exactly the founders those signals touched. Cheap when nothing is new (one empty query)."""
    db = SessionLocal()
    try:
        return run_claims(db)
    finally:
        db.close()
