"""Founder axis — DETERMINISTIC projection of the persistent Founder Score (prd item 3).

No LLM. The Founder Score (app.claims.score) is the number; this module bands it into a
verdict, derives the trend arrow from score_history, and sizes confidence by evidence mass.
Cold-start rule: limited evidence is NOT negative evidence — a low score backed by few claims
stays neutral (low confidence), never bear.

Bands calibrated to the live saturating formula (K=3: strong founders land ~40-50 today).
"""

import uuid
from math import exp
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvidence, Founder, Opportunity, ScoreHistory, Signal, ThreeAxis

BULL_AT_LEAST = 40.0
BEAR_BELOW = 15.0
COLD_START_MIN_CLAIMS = 6  # below this, a low score is evidence-poverty, not weakness
CONFIDENCE_K = 5.0  # confidence = 1 - e^(-sum(trust)/K), same saturating family as the score
CONFIDENCE_CAP = 0.95
TREND_DEADBAND = 1.0  # |delta| below this is noise, not a trend


class FounderAxisResult(BaseModel):
    score: float | None
    verdict: Literal["bull", "neutral", "bear"]
    trend: Literal["improving", "declining", "stable"]
    confidence: float
    rationale: str
    evidence: dict  # {"claim_ids": [...], "urls": [...]} — same shape as the market axis
    gaps: list[str]


def compute_founder_axis(
    *,
    founder_score: float | None,
    components: dict | None,
    claims: list[dict],  # [{"id": str, "trust": float|None, "urls": [str]}]
    history_scores: list[float],  # Founder Score points, chronological
) -> FounderAxisResult:
    n = len(claims)
    cold_start = n < COLD_START_MIN_CLAIMS
    evidence_mass = sum(c["trust"] or 0.0 for c in claims)
    confidence = round(min(CONFIDENCE_CAP, 1.0 - exp(-evidence_mass / CONFIDENCE_K)), 2)
    gaps: list[str] = []
    parts: list[str] = []

    if founder_score is None:
        if claims:
            raise RuntimeError(
                f"{n} claims but founder_score is None — run the claims rescore first"
            )
        verdict: Literal["bull", "neutral", "bear"] = "neutral"
        gaps.append("no claims yet — Founder Score not computed")
        parts.append("No claims on record; Founder Score not yet computed — neutral by default.")
    else:
        if founder_score >= BULL_AT_LEAST:
            verdict = "bull"
        elif founder_score < BEAR_BELOW and not cold_start:
            verdict = "bear"
        else:
            verdict = "neutral"
        comp = {k: v for k, v in (components or {}).items() if k != "momentum"}
        comp_str = ", ".join(f"{k} {v}" for k, v in sorted(comp.items(), key=lambda kv: -kv[1]))
        parts.append(
            f"Founder Score {founder_score}/100 from {n} claims"
            + (f" ({comp_str})" if comp_str else "")
            + f". Verdict {verdict} (bands: bull >= {BULL_AT_LEAST:g}, "
            + f"bear < {BEAR_BELOW:g} with >= {COLD_START_MIN_CLAIMS} claims)."
        )

    if cold_start and n > 0:
        note = (
            f"cold-start: only {n} claims (< {COLD_START_MIN_CLAIMS}) — "
            "limited evidence, not negative evidence"
        )
        gaps.append(note)
        parts.append(note + "; confidence lowered, verdict not penalized.")

    if len(history_scores) < 2:
        trend: Literal["improving", "declining", "stable"] = "stable"
        gaps.append(
            f"score history has {len(history_scores)} point(s) — trend defaults to stable"
        )
        parts.append("Trend stable (insufficient score history).")
    else:
        delta = history_scores[-1] - history_scores[-2]
        if delta >= TREND_DEADBAND:
            trend = "improving"
        elif delta <= -TREND_DEADBAND:
            trend = "declining"
        else:
            trend = "stable"
        parts.append(f"Trend {trend} ({delta:+.1f} vs previous score point).")

    return FounderAxisResult(
        score=founder_score,
        verdict=verdict,
        trend=trend,
        confidence=confidence,
        rationale=" ".join(parts),
        evidence={
            "claim_ids": [c["id"] for c in claims],
            "urls": sorted({u for c in claims for u in c["urls"]}),
        },
        gaps=gaps,
    )


def upsert_founder_axis(db: Session, opportunity_id: uuid.UUID) -> ThreeAxis:
    """Compute + upsert the three_axis row axis='founder' for an opportunity.

    Flushes but does NOT commit — composable into the item-6 assembler transaction.
    """
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")
    if opp.founder_id is None:
        raise ValueError(
            f"opportunity {opportunity_id} has no founder — founder axis needs a person"
        )
    founder = db.get(Founder, opp.founder_id)
    assert founder is not None  # FK guarantees the row
    claim_rows = db.execute(
        select(Claim.id, Claim.trust_score).where(Claim.founder_id == founder.id)
    ).all()
    urls_by_claim: dict[uuid.UUID, list[str]] = {cid: [] for cid, _ in claim_rows}
    if urls_by_claim:
        for cid, url in db.execute(
            select(ClaimEvidence.claim_id, Signal.url)
            .join(Signal, ClaimEvidence.signal_id == Signal.id)
            .where(
                ClaimEvidence.claim_id.in_(urls_by_claim),
                ClaimEvidence.stance == "supports",
                Signal.url.isnot(None),
            )
        ).all():
            urls_by_claim[cid].append(url)
    claims = [
        {"id": str(cid), "trust": trust, "urls": urls_by_claim[cid]} for cid, trust in claim_rows
    ]
    history = [
        s
        for (s,) in db.execute(
            select(ScoreHistory.score)
            .where(ScoreHistory.founder_id == founder.id, ScoreHistory.score.isnot(None))
            .order_by(ScoreHistory.created_at)
        ).all()
    ]
    result = compute_founder_axis(
        founder_score=founder.founder_score,
        components=founder.components,
        claims=claims,
        history_scores=history,
    )
    row = (
        db.execute(
            select(ThreeAxis).where(
                ThreeAxis.opportunity_id == opp.id, ThreeAxis.axis == "founder"
            )
        )
        .scalars()
        .first()
    )
    if row is None:
        row = ThreeAxis(opportunity_id=opp.id, axis="founder")
        db.add(row)
    row.score = result.score
    row.verdict = result.verdict
    row.trend = result.trend
    row.confidence = result.confidence
    row.rationale = result.rationale
    row.evidence = result.evidence
    row.gaps = result.gaps
    db.flush()
    return row
