"""Inbound application intake — the funnel's inbound track (ported from BE/).

POST /apply lands here. Flow (synchronous, two fast-LLM calls):
  1. create the Opportunity (source='inbound', status='screening')
  2. parse the deck into per-page signals (idempotent upsert)
  3. one extraction call -> idea/sector/geo + checkable deck claims
  4. pre-screen: deterministic thesis hard filters in code, then LLM viability (uncertain -> pass)
  5. mint opportunity-anchored claims, claim_evidence -> deck-page signals, trust via the shared
     deterministic formula (one low-reliability source -> stays 'unverified' until corroborated)

Reject != delete: a rejected application keeps its opportunity row, signals, and claims; the
reason lands in a trace_step row (provenance). Full 3-axis screening stays manual-dispatch
(POST /opportunities/{id}/screen), same as the outbound track.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims import trust as trust_mod
from app.inbound.deck import DECK_SOURCE_RELIABILITY, parse_deck
from app.inbound.extract import DeckClaim, PreScreenResult, extract_deck, prescreen_llm
from app.ingest import upsert_signal
from app.models import Claim, ClaimEvidence, InvestmentThesis, Opportunity, Signal, TraceStep

_RELEVANCE = 0.85  # deck page directly asserts the claim (mirrors app.claims.service)


def hard_filter(
    thesis: InvestmentThesis | None, sector: str | None, geo: str | None
) -> PreScreenResult | None:
    """Deterministic thesis filters — a miss rejects without spending an LLM call.
    Loose match (substring either way) so 'healthtech' vs 'healthcare' doesn't hard-kill."""
    if thesis is None:
        return None
    for value, allowed, label in ((sector, thesis.industries, "sector"), (geo, thesis.geo, "geo")):
        if not (allowed and value):
            continue
        v = value.lower()
        if not any(v in a.lower() or a.lower() in v for a in allowed):
            return PreScreenResult(
                verdict="reject",
                reason=f"Thesis hard filter: {label}='{value}' not in {allowed}",
            )
    return None


def _thesis_dict(thesis: InvestmentThesis | None) -> dict:
    if thesis is None:
        return {}
    return {
        "name": thesis.name,
        "industries": thesis.industries,
        "geo": thesis.geo,
        "stage": thesis.stage,
        "keywords": thesis.keywords,
        "founder_preferences": thesis.founder_preferences,
    }


def _mint_deck_claims(
    db: Session,
    opp: Opportunity,
    extracted: list[DeckClaim],
    signal_by_page: dict[int, Signal],
) -> tuple[int, int]:
    """Mint opportunity-anchored claims, evidence -> deck-page signals. Returns (minted, dropped).
    No resolvable page citation -> dropped (the claims-layer anti-hallucination rule)."""
    minted = dropped = 0
    weight = trust_mod.evidence_weight(DECK_SOURCE_RELIABILITY, 1.0, _RELEVANCE)
    for ec in extracted:
        sig = signal_by_page.get(ec.source_page)
        if sig is None or not ec.statement.strip():
            dropped += 1
            continue
        claim = Claim(
            opportunity_id=opp.id,
            category=ec.category,
            statement=ec.statement,
            attributes={"source_pointer": f"deck p.{ec.source_page}"},
            status="unverified",
        )
        db.add(claim)
        db.flush()
        db.add(
            ClaimEvidence(
                claim_id=claim.id,
                signal_id=sig.id,
                stance="supports",
                weight=weight,
                extraction_conf=_RELEVANCE,
                rationale=f"asserted in deck p.{ec.source_page}",
            )
        )
        claim.trust_score = trust_mod.trust_score([weight], [])
        claim.status = trust_mod.derive_status(claim.trust_score, [])
        claim.trust_components = trust_mod.trust_components([weight], [], ["inbound"])
        minted += 1
    return minted, dropped


def run_inbound_application(db: Session, *, company_name: str, deck_bytes: bytes) -> dict:
    name = company_name.strip()
    if not name:
        raise ValueError("company_name is empty")

    opp = Opportunity(company_name=name, source="inbound", status="screening")
    db.add(opp)
    db.flush()

    envelopes = parse_deck(deck_bytes, name, opp.id)  # raises on empty/text-free PDFs
    signal_by_page: dict[int, Signal] = {}
    for env in envelopes:
        sig, _created = upsert_signal(db, env)
        signal_by_page[env.raw["page"]] = sig
    pages = [(env.raw["page"], env.raw["text"]) for env in envelopes]

    extraction = extract_deck(name, pages)
    opp.idea = extraction.idea
    opp.sector = extraction.sector
    opp.geo = extraction.geo

    thesis = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    pre = hard_filter(thesis, extraction.sector, extraction.geo) or prescreen_llm(
        _thesis_dict(thesis), pages
    )

    # Mint claims regardless of verdict — a rejection keeps its evidence trail queryable.
    minted, dropped = _mint_deck_claims(db, opp, extraction.claims, signal_by_page)

    if pre.verdict == "reject":
        opp.status = "rejected"

    db.add(
        TraceStep(
            opportunity_id=opp.id,
            stage="screen",
            agent="inbound_intake",
            input={"company_name": name, "deck_pages": len(pages)},
            output={
                "prescreen": pre.verdict,
                "reason": pre.reason,
                "claims_minted": minted,
                "claims_dropped": dropped,
                "idea": opp.idea,
                "sector": opp.sector,
                "geo": opp.geo,
            },
            evidence_ids=[str(s.id) for s in signal_by_page.values()],
        )
    )
    db.commit()

    return {
        "opportunity_id": str(opp.id),
        "status": opp.status,
        "prescreen_verdict": pre.verdict,
        "prescreen_reason": pre.reason,
        "signals_ingested": len(signal_by_page),
        "claims_minted": minted,
        "idea": opp.idea,
        "sector": opp.sector,
        "geo": opp.geo,
    }
