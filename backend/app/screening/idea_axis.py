"""Idea-vs-Market axis (prd item 5) — LLM verdict with deterministic anchors.

The question the brief asks: does the idea survive scrutiny AS-IS, or is the team strong enough
to PIVOT, or does it FAIL? Judged over the founder's claims (the team) + the market findings
(the market axis + market-level claims). Independent of the other axes — it reads their inputs,
never their verdicts, and is NEVER averaged with them.

Anchors (hard floor, deterministic): every cited claim id must resolve to a claim we actually
passed in (no fabrication); cold-start (thin team evidence) lowers CONFIDENCE, never the score.
"""

import uuid
from typing import Literal, cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvidence, Opportunity, Signal, ThreeAxis
from app.screening.llm import structured_llm

# survives_as_is -> the idea holds -> bull; pivot_needed -> neutral; fails -> bear.
_VERDICT_MAP: dict[str, Literal["bull", "neutral", "bear"]] = {
    "survives_as_is": "bull",
    "pivot_needed": "neutral",
    "fails": "bear",
}
COLD_START_MIN_TEAM_CLAIMS = 6  # below this the team read is evidence-poor, not weak


class IdeaAxisLLM(BaseModel):
    """Structured LLM output for the idea-vs-market judgment."""

    verdict: Literal["survives_as_is", "pivot_needed", "fails"]
    score: float = Field(ge=0.0, le=100.0, description="idea-vs-market attractiveness, thesis-relative")
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(description="grounded in the cited claims; names the evidence it rests on")
    evidence_claim_ids: list[str] = Field(
        default_factory=list, description="ids of the provided claims this verdict rests on"
    )
    gaps: list[str] = Field(default_factory=list, description="what's missing/unverified to decide")


class IdeaAxisResult(BaseModel):
    verdict: Literal["bull", "neutral", "bear"]
    score: float
    trend: Literal["improving", "declining", "stable"]
    confidence: float
    rationale: str
    evidence: dict
    gaps: list[str]


def _claims_block(label: str, claims: list[dict]) -> str:
    if not claims:
        return f"## {label}\n(none on record)"
    lines = "\n".join(
        f"[{c['id']}] ({c['category']}, trust={c['trust']}) {c['statement']}" for c in claims
    )
    return f"## {label}\n{lines}"


def assess_idea_axis(
    *,
    opportunity: dict,  # {idea, sector, company_name}
    founder_claims: list[dict],  # [{id, statement, category, trust}]
    market_claims: list[dict],  # [{id, statement, category, trust}]
    market_summary: str | None,  # the market axis rationale, if screened
) -> tuple[IdeaAxisResult, IdeaAxisLLM]:
    valid_ids = {c["id"] for c in founder_claims} | {c["id"] for c in market_claims}
    prompt = f"""You are a VC analyst scoring the IDEA-vs-MARKET axis for an opportunity — ONE of three
independent axes (never averaged with the others).

## Opportunity
idea: {opportunity.get("idea")}
sector: {opportunity.get("sector")}
company: {opportunity.get("company_name")}

## Market findings (from the market axis)
{market_summary or "(market not yet analyzed)"}

{_claims_block("Founder / team evidence (claims)", founder_claims)}

{_claims_block("Market evidence (claims)", market_claims)}

## Task
Judge whether the idea, as stated, survives scrutiny against this market:
- verdict='survives_as_is' — the idea is well-matched to the market as-is.
- verdict='pivot_needed' — the idea has gaps, BUT the team is strong enough to find an adjacent win.
- verdict='fails' — weak idea AND no evidence the team can pivot into something better.

## Rules
1. Base the verdict ONLY on the evidence above. Cite the claim ids you rely on in evidence_claim_ids
   — use ONLY ids shown in [brackets]; never invent an id or a fact.
2. Thin team evidence is NOT a negative — it lowers CONFIDENCE, never forces 'fails'. If the team has
   few claims, prefer 'pivot_needed'/'survives_as_is' with low confidence and say so in gaps.
3. score 0..100 = idea-vs-market attractiveness; confidence 0..1 = how sure the evidence lets you be.
4. Be specific and concise. Name the market dynamic and the team signal that drive the call.

Return the structured judgment now."""
    out = cast(IdeaAxisLLM, structured_llm(IdeaAxisLLM, smart=True).invoke(prompt))
    return finalize_idea(out, valid_ids=valid_ids, n_founder_claims=len(founder_claims)), out


def finalize_idea(
    out: IdeaAxisLLM, *, valid_ids: set[str], n_founder_claims: int
) -> IdeaAxisResult:
    """Deterministic post-processing (pure, testable): anti-fabrication anchor + cold-start rule.

    - drops any cited claim id not in the evidence we actually passed (no hallucinated provenance);
    - cold-start (thin team evidence) caps confidence, NEVER changes the verdict.
    """
    resolved = [cid for cid in out.evidence_claim_ids if cid in valid_ids]
    hallucinated = [cid for cid in out.evidence_claim_ids if cid not in valid_ids]
    gaps = list(out.gaps)
    if hallucinated:
        gaps.append(f"dropped {len(hallucinated)} cited id(s) not in the evidence set")
    confidence = out.confidence
    if n_founder_claims < COLD_START_MIN_TEAM_CLAIMS:
        confidence = min(confidence, 0.5)
        gaps.append(
            f"thin team evidence ({n_founder_claims} founder claims) — confidence capped, "
            "verdict not penalized"
        )
    return IdeaAxisResult(
        verdict=_VERDICT_MAP[out.verdict],
        score=out.score,
        trend="stable",  # no idea-axis history yet; first pass reads stable
        confidence=round(confidence, 2),
        rationale=out.rationale,
        evidence={"claim_ids": resolved, "urls": []},
        gaps=gaps,
    )


def upsert_idea_axis(db: Session, opportunity_id: uuid.UUID) -> ThreeAxis:
    """Gather founder + market evidence, run the LLM, upsert the three_axis row axis='idea'.

    Flushes but does NOT commit — composable into the item-6 assembler transaction.
    """
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")
    if not (opp.idea or opp.sector):
        raise ValueError(f"opportunity {opportunity_id} has no idea/sector — nothing to judge")

    def _claims(rows) -> list[dict]:
        return [
            {"id": str(cid), "statement": st, "category": cat, "trust": tr}
            for cid, st, cat, tr in rows
        ]

    founder_claims = (
        _claims(
            db.execute(
                select(Claim.id, Claim.statement, Claim.category, Claim.trust_score).where(
                    Claim.founder_id == opp.founder_id
                )
            ).all()
        )
        if opp.founder_id
        else []
    )
    market_claims = _claims(
        db.execute(
            select(Claim.id, Claim.statement, Claim.category, Claim.trust_score).where(
                Claim.opportunity_id == opp.id
            )
        ).all()
    )
    market_row = (
        db.execute(
            select(ThreeAxis).where(ThreeAxis.opportunity_id == opp.id, ThreeAxis.axis == "market")
        )
        .scalars()
        .first()
    )
    market_summary = (
        f"verdict={market_row.verdict}, score={market_row.score}: {market_row.rationale}"
        if market_row
        else None
    )

    result, _ = assess_idea_axis(
        opportunity={"idea": opp.idea, "sector": opp.sector, "company_name": opp.company_name},
        founder_claims=founder_claims,
        market_claims=market_claims,
        market_summary=market_summary,
    )

    # provenance urls for the resolved founder-claim ids (market claims carry their own via signals)
    resolved_ids = [uuid.UUID(c) for c in result.evidence["claim_ids"]]
    if resolved_ids:
        urls = [
            u
            for (u,) in db.execute(
                select(Signal.url)
                .join(ClaimEvidence, ClaimEvidence.signal_id == Signal.id)
                .where(ClaimEvidence.claim_id.in_(resolved_ids), Signal.url.isnot(None))
            ).all()
        ]
        result.evidence["urls"] = sorted(set(urls))

    row = (
        db.execute(
            select(ThreeAxis).where(ThreeAxis.opportunity_id == opp.id, ThreeAxis.axis == "idea")
        )
        .scalars()
        .first()
    )
    if row is None:
        row = ThreeAxis(opportunity_id=opp.id, axis="idea")
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
