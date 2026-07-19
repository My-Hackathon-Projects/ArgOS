"""Single-writer persist for a market analysis. Idempotent — safe to re-run per opportunity.

Writes, in one transaction:
  - opportunity (+ optional company / founder_company) if not passed an existing id,
  - one `web` signal per cited hit (founder_id NULL -> never enters the founder-claim pipeline),
  - market claims (category market_size|market|competition|comparable), opportunity-anchored,
    each with claim_evidence(stance='supports') and a deterministic trust_score REUSING
    app.claims.trust (the shared formula — no parallel trust model),
  - the three_axis 'market' row (upsert on (opportunity_id, axis)).

Every figure/competitor/comparable that lacks resolvable evidence is dropped (no citation ->
no claim), matching the claims-layer anti-hallucination rule. Gap-flagged figures are recorded in
three_axis.gaps, not fabricated into claims.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims import trust as trust_mod
from app.market.graph import extractor_hits
from app.models import (
    Claim,
    ClaimEvidence,
    Company,
    FounderCompany,
    JobRun,
    Opportunity,
    Signal,
    ThreeAxis,
)
from app.sourcing.graph import SOURCE_RELIABILITY, _canonicalize, _infer_source

_SIGNAL_TYPE = {
    "sizing": "market_size",
    "trend": "market_trend",
    "competition": "competitor",
    "comparables": "funding",
    "kpi": "benchmark",
}


def _uuid(v) -> uuid.UUID | None:
    if v is None or isinstance(v, uuid.UUID):
        return v
    return uuid.UUID(str(v))


def _upsert_opportunity(db: Session, opp: dict, opportunity_id) -> Opportunity:
    if opportunity_id:
        row = db.get(Opportunity, _uuid(opportunity_id))
        if row is None:
            raise ValueError(f"opportunity {opportunity_id} not found")
        return row
    founder_id = _uuid(opp.get("founder_id"))
    company_id = None
    if opp.get("company_name"):
        company = Company(
            name=opp["company_name"],
            sector=opp.get("sector"),
            geo=opp.get("geo"),
            description=opp.get("idea"),
        )
        db.add(company)
        db.flush()
        company_id = company.id
        if founder_id:
            db.add(FounderCompany(founder_id=founder_id, company_id=company_id, role="founder"))
    row = Opportunity(
        founder_id=founder_id,
        company_id=company_id,
        company_name=opp.get("company_name"),
        idea=opp.get("idea"),
        sector=opp.get("sector"),
        geo=opp.get("geo"),
        source="outbound",
        status="diligence",
    )
    db.add(row)
    db.flush()
    return row


def _mint_signals(db: Session, hits_by_goal: dict) -> dict:
    """One `web` signal per unique cited URL -> {canonical_url: signal_id} (incl. existing)."""
    canon_map: dict[str, uuid.UUID] = {}
    all_canon = {
        _canonicalize(h["url"]) for hits in hits_by_goal.values() for h in hits if h.get("url")
    }
    all_canon.discard(None)
    if all_canon:
        for sid, curl in db.execute(
            select(Signal.id, Signal.canonical_url).where(Signal.canonical_url.in_(all_canon))
        ).all():
            canon_map[curl] = sid
    for sg, hits in hits_by_goal.items():
        for h in hits:
            url = h.get("url")
            canon = _canonicalize(url) if url else None
            if not canon or canon in canon_map:
                continue
            src = _infer_source(canon)
            sig = Signal(
                source=src,
                signal_type=_SIGNAL_TYPE.get(sg, "market"),
                external_id=canon,
                canonical_url=canon,
                content_hash=None,  # canonical_url dedup suffices; avoids hash-unique clashes
                url=url,
                title=h.get("title"),
                summary=(h.get("content") or "")[:500],
                source_reliability=SOURCE_RELIABILITY.get(src, 0.4),
                sources_seen=[src],
                founder_id=None,  # market signals are NOT founder-linked
                raw=h,
            )
            db.add(sig)
            db.flush()
            canon_map[canon] = sig.id
    return canon_map


def _recompute_trust(db: Session, claim: Claim) -> None:
    """Deterministic trust over the claim's evidence — the SAME formula as founder claims."""
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


def _persist_claims(db: Session, opp_id, analysis: dict, canon_map: dict) -> tuple[list, list]:
    eh = extractor_hits(analysis.get("hits_by_goal") or {})
    existing = {
        c.dedup_key: c
        for c in db.execute(
            select(Claim).where(Claim.opportunity_id == opp_id, Claim.dedup_key.isnot(None))
        ).scalars()
    }
    edge_seen: set = set()
    for cid, sid in db.execute(
        select(ClaimEvidence.claim_id, ClaimEvidence.signal_id)
        .join(Claim, ClaimEvidence.claim_id == Claim.id)
        .where(Claim.opportunity_id == opp_id)
    ).all():
        edge_seen.add((cid, sid))

    touched: dict = {}
    cited_urls: set = set()

    def _sigs(extractor: str, indices: list[int]) -> list:
        hits = eh.get(extractor) or []
        out = []
        for i in indices or []:
            if 0 <= i < len(hits):
                canon = _canonicalize(hits[i].get("url") or "")
                sid = canon_map.get(canon)
                if sid:
                    out.append((sid, canon))
        return out

    def _upsert(category, statement, dedup_key, attributes, extractor, indices, relevance):
        sigs = _sigs(extractor, indices)
        if not sigs:
            return None  # no resolvable citation -> reject (anti-hallucination)
        claim = existing.get(dedup_key)
        if claim is None:
            claim = Claim(
                opportunity_id=opp_id,
                founder_id=None,
                category=category,
                statement=statement,
                attributes=attributes,
                dedup_key=dedup_key,
                status="unverified",
            )
            db.add(claim)
            db.flush()
            existing[dedup_key] = claim
        for sid, canon in sigs:
            cited_urls.add(canon)
            if (claim.id, sid) in edge_seen:
                continue
            edge_seen.add((claim.id, sid))
            sig = db.get(Signal, sid)
            db.add(
                ClaimEvidence(
                    claim_id=claim.id,
                    signal_id=sid,
                    stance="supports",
                    weight=trust_mod.evidence_weight(
                        sig.source_reliability, sig.resolution_confidence, relevance
                    ),
                    extraction_conf=relevance,
                )
            )
        touched[claim.id] = claim
        return claim

    for fig in (analysis.get("sizing") or {}).get("figures", []):
        if fig.get("basis") == "gap" or not fig.get("value"):
            continue
        m = fig["metric"]
        _upsert(
            "market_size",
            f"{m}: {fig['value']} ({fig['basis']})",
            f"market_size:{m.lower()}",
            {
                k: fig.get(k)
                for k in ("metric", "value", "unit", "basis", "assumptions", "confidence")
            },
            "sizing",
            fig.get("citation_indices"),
            fig.get("confidence") or 0.7,
        )

    for fig in (analysis.get("kpi") or {}).get("benchmarks", []):
        if fig.get("basis") == "gap" or not fig.get("value"):
            continue
        m = fig["metric"]
        _upsert(
            "market",
            f"{m} benchmark: {fig['value']}",
            f"kpi:{m.lower()}",
            {k: fig.get(k) for k in ("metric", "value", "unit", "basis", "confidence")},
            "kpi",
            fig.get("citation_indices"),
            fig.get("confidence") or 0.7,
        )

    for comp in (analysis.get("competition") or {}).get("competitors", []):
        name = (comp.get("name") or "").strip()
        if not name:
            continue
        _upsert(
            "competition",
            f"Competitor: {name} — {comp.get('positioning', '')}".strip(" —"),
            f"competitor:{name.lower()}",
            {k: comp.get(k) for k in ("cluster", "positioning", "is_emerging_threat")},
            "competition",
            comp.get("citation_indices"),
            0.8,
        )

    for cmp in (analysis.get("comparables") or {}).get("comparables", []):
        name = (cmp.get("name") or "").strip()
        if not name:
            continue
        rs = cmp.get("round_size") or "undisclosed amount"
        _upsert(
            "comparable",
            f"Comparable: {name} raised {rs} ({cmp.get('stage') or 'stage n/a'})",
            f"comparable:{name.lower()}",
            {
                k: cmp.get(k)
                for k in (
                    "one_liner",
                    "stage",
                    "round_size",
                    "valuation",
                    "investors",
                    "date",
                    "similarity_rationale",
                    "confidence",
                )
            },
            "comparables",
            cmp.get("citation_indices"),
            cmp.get("confidence") or 0.7,
        )

    db.flush()
    for claim in touched.values():
        _recompute_trust(db, claim)
    return list(touched.keys()), sorted(cited_urls)


def _gap_figures(analysis: dict) -> list[str]:
    gaps = []
    for section in ("sizing", "kpi"):
        figs = (analysis.get(section) or {}).get("figures") or (analysis.get(section) or {}).get(
            "benchmarks", []
        )
        for f in figs:
            if f.get("basis") == "gap":
                gaps.append(f"{f.get('metric')}: not found / unverified")
    return gaps


def _upsert_axis(
    db: Session, opp_id, analysis: dict, claim_ids: list, cited_urls: list
) -> ThreeAxis:
    axis = (analysis.get("synthesis") or {}).get("axis") or {}
    synthesis = analysis.get("synthesis") or {}
    row = (
        db.execute(
            select(ThreeAxis).where(ThreeAxis.opportunity_id == opp_id, ThreeAxis.axis == "market")
        )
        .scalars()
        .first()
    )
    if row is None:
        row = ThreeAxis(opportunity_id=opp_id, axis="market")
        db.add(row)
    row.score = axis.get("score")
    row.verdict = axis.get("verdict") or "neutral"
    row.trend = axis.get("trend") or "stable"
    row.rationale = axis.get("rationale")
    row.confidence = axis.get("confidence")
    row.evidence = {"claim_ids": [str(c) for c in claim_ids], "urls": cited_urls}
    row.gaps = (synthesis.get("gaps") or []) + _gap_figures(analysis)
    return row


def persist_market(db: Session, analysis: dict, opportunity_id=None) -> dict:
    job = JobRun(source="market")
    db.add(job)
    db.flush()

    opp = _upsert_opportunity(db, analysis["opportunity"], opportunity_id)
    canon_map = _mint_signals(db, analysis.get("hits_by_goal") or {})
    claim_ids, cited_urls = _persist_claims(db, opp.id, analysis, canon_map)
    axis_row = _upsert_axis(db, opp.id, analysis, claim_ids, cited_urls)

    job.finished_at = datetime.now(UTC)
    job.new_signals = len(canon_map)
    db.commit()
    return {
        "opportunity_id": str(opp.id),
        "signals": len(canon_map),
        "claims": len(claim_ids),
        "cited_urls": len(cited_urls),
        "market_axis": {
            "verdict": axis_row.verdict,
            "score": axis_row.score,
            "trend": axis_row.trend,
            "confidence": axis_row.confidence,
        },
        "gaps": axis_row.gaps,
        "job_run_id": str(job.id),
    }
