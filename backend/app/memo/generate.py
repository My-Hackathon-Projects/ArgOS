"""Mini investment memo (prd item 7) — LLM prose + deterministic anchors.

Focused, not the full Appendix-1: Company snapshot, 2-3 evidence-backed Investment hypotheses,
short SWOT, Recommendation + confidence, explicit Gaps. Written over the opportunity's claims +
market findings + the 3 axes — and it NEVER averages the axes; it surfaces their disagreement.

Deterministic anchors (the Trust floor, not the LLM's word):
- every hypothesis citation must resolve to a claim we passed in (else it's dropped + gapped);
- required sections must be present (else recorded as a gap);
- missing data is flagged explicitly, never fabricated.
"""

import uuid
from typing import cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvidence, Memo, Opportunity, Signal, ThreeAxis
from app.screening.llm import structured_llm

REQUIRED_SECTIONS = ("snapshot", "hypotheses", "swot", "recommendation")


class MemoHypothesis(BaseModel):
    statement: str
    evidence_claim_ids: list[str] = Field(
        default_factory=list, description="ids of the claims this hypothesis rests on"
    )


class MemoSWOT(BaseModel):
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    threats: list[str] = Field(default_factory=list)


class MemoLLM(BaseModel):
    snapshot: str = Field(
        description="one-paragraph 'in a nutshell': market, problem, why now, product"
    )
    hypotheses: list[MemoHypothesis] = Field(description="2-3 evidence-backed 'why invest' bullets")
    swot: MemoSWOT
    recommendation: str = Field(
        description="invest / track / pass + why; must reflect the 3 axes, NEVER average them"
    )
    confidence: float = Field(ge=0.0, le=1.0)
    gaps: list[str] = Field(
        default_factory=list,
        description="explicitly-flagged missing data (e.g. 'Cap table: not disclosed')",
    )


def _claims_block(label: str, claims: list[dict]) -> str:
    if not claims:
        return f"## {label}\n(none)"
    return f"## {label}\n" + "\n".join(
        f"[{c['id']}] ({c['category']}, trust={c['trust']}) {c['statement']}" for c in claims
    )


def _axes_block(axes: list[ThreeAxis]) -> str:
    return "\n".join(
        f"- {a.axis}: {a.verdict} (score {a.score}, {a.trend}) — {(a.rationale or '')[:220]}"
        for a in sorted(axes, key=lambda a: {"founder": 0, "market": 1, "idea": 2}[a.axis])
    )


def generate_memo(db: Session, opportunity_id: uuid.UUID) -> Memo:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")
    axes = list(opp.axes)
    if not axes:
        raise ValueError(f"opportunity {opportunity_id} not screened yet — run /screen first")

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
    valid_ids = {c["id"] for c in founder_claims} | {c["id"] for c in market_claims}

    prompt = f"""You are a VC writing a CONCISE investment memo for a $100K decision. As detailed as the
decision needs, as brief as clarity allows — padding counts against you.

## Opportunity
company: {opp.company_name}
idea: {opp.idea}
sector: {opp.sector}   geo: {opp.geo}

## 3-axis screen (INDEPENDENT — never average them; the disagreement is the signal)
{_axes_block(axes)}

{_claims_block("Founder / team claims", founder_claims)}

{_claims_block("Market claims", market_claims)}

## Task — write a mini memo
- snapshot: one paragraph (market, the structural problem, why now, how the product solves it).
- hypotheses: 2-3 'why we'd invest' bullets, EACH citing the claim ids it rests on (evidence_claim_ids).
- swot: short, evidence-backed strengths/weaknesses/opportunities/threats.
- recommendation: invest / track / pass, with a reason that REFLECTS all three axes (if an axis is bear,
  say how you weigh it — do not silently ignore or average it).
- confidence 0..1.
- gaps: list what's missing/unknown EXPLICITLY (e.g. 'Cap table: not disclosed', 'No revenue evidence').
  A memo that marks its own gaps is more trustworthy than one that hides them.

## Rules
1. Cite ONLY claim ids shown in [brackets]; never invent an id, a number, or a fact.
2. If a required data point is absent, put it in gaps — do NOT fabricate it.
3. Be specific and concise."""

    out = cast(MemoLLM, structured_llm(MemoLLM, smart=True).invoke(prompt))

    # ── deterministic anchors ────────────────────────────────────────────────
    gaps = list(out.gaps)
    dropped = 0
    resolved_hyps = []
    for h in out.hypotheses:
        resolved = [cid for cid in h.evidence_claim_ids if cid in valid_ids]
        dropped += len(h.evidence_claim_ids) - len(resolved)
        resolved_hyps.append({"statement": h.statement, "evidence_claim_ids": resolved})
    if dropped:
        gaps.append(f"dropped {dropped} hypothesis citation(s) not in the evidence set")

    sections = {
        "snapshot": out.snapshot,
        "hypotheses": resolved_hyps,
        "swot": out.swot.model_dump(),
        "axes": [
            {"axis": a.axis, "verdict": a.verdict, "score": a.score, "trend": a.trend}
            for a in sorted(axes, key=lambda a: {"founder": 0, "market": 1, "idea": 2}[a.axis])
        ],
    }
    missing = [s for s in REQUIRED_SECTIONS if s != "recommendation" and not sections.get(s)]
    for s in missing:
        gaps.append(f"required section missing: {s}")

    # provenance urls for every resolved hypothesis citation
    all_ids = [uuid.UUID(cid) for h in resolved_hyps for cid in h["evidence_claim_ids"]]
    urls: list[str] = []
    if all_ids:
        urls = sorted(
            {
                u
                for (u,) in db.execute(
                    select(Signal.url)
                    .join(ClaimEvidence, ClaimEvidence.signal_id == Signal.id)
                    .where(ClaimEvidence.claim_id.in_(all_ids), Signal.url.isnot(None))
                ).all()
            }
        )

    quality = {
        "all_citations_resolved": dropped == 0,
        "required_sections_present": not missing,
        "n_hypotheses": len(resolved_hyps),
        "provenance_urls": urls,
    }

    row = db.execute(select(Memo).where(Memo.opportunity_id == opp.id)).scalars().first()
    if row is None:
        row = Memo(opportunity_id=opp.id)
        db.add(row)
    row.sections = sections
    row.recommendation = out.recommendation
    row.confidence = out.confidence
    row.gaps = gaps
    row.quality = quality
    db.commit()
    db.refresh(row)
    return row
