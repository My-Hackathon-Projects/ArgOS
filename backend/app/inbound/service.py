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

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.claims import trust as trust_mod
from app.companies import link_founder_company, resolve_company
from app.inbound.deck import DECK_SOURCE_RELIABILITY, parse_deck
from app.inbound.extract import DeckClaim, PreScreenResult, extract_deck, prescreen_llm
from app.ingest import upsert_signal
from app.models import (
    Claim,
    ClaimEvidence,
    InvestmentThesis,
    Opportunity,
    Signal,
    TraceStep,
    founder_signal,
)
from app.sourcing.persist import resolve_or_create_founder

_RELEVANCE = 0.85  # deck page directly asserts the claim (mirrors app.claims.service)


def hard_filter(thesis: InvestmentThesis | None, sector: str | None) -> PreScreenResult | None:
    """Deterministic thesis sector filter — a miss rejects without spending an LLM call.
    Loose match (substring either way) so 'healthtech' vs 'healthcare' doesn't hard-kill.
    Geo is deliberately NOT hard-filtered: containment ('EU' vs 'Munich') needs semantics
    a string match can't see — the LLM prescreen judges it (uncertain -> pass)."""
    if thesis is None or not (thesis.industries and sector):
        return None
    v = sector.lower()
    if not any(v in a.lower() or a.lower() in v for a in thesis.industries):
        return PreScreenResult(
            verdict="reject",
            reason=f"Thesis hard filter: sector='{sector}' not in {thesis.industries}",
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
        trust = trust_mod.trust_score([weight], [])
        claim.trust_score = trust
        claim.status = trust_mod.derive_status(trust, [])
        claim.trust_components = trust_mod.trust_components([weight], [], ["inbound"])
        minted += 1
    return minted, dropped


def run_inbound_application(db: Session, *, company_name: str, deck_bytes: bytes) -> dict:
    name = company_name.strip()
    if not name:
        raise ValueError("company_name is empty")

    # The venture is resolved before the deal exists, so an inbound application for a company
    # we already track attaches to that company rather than minting a second one.
    company = resolve_company(db, name=name)

    # The deal's id is minted up front but the row is NOT created yet: founder_id is NOT NULL,
    # and the founder is only knowable after the deck is parsed and extracted. Deck signals key
    # off this id (external_id only — no FK), so nothing needs the row to exist first.
    opp_id = uuid.uuid4()
    envelopes = parse_deck(deck_bytes, name, opp_id)  # raises on empty/text-free PDFs
    pages = [(env.raw["page"], env.raw["text"]) for env in envelopes]
    extraction = extract_deck(name, pages)

    # Founder-first: a deck we cannot attribute to a person is not a deal. Rejecting here is the
    # point — a founderless opportunity has no founder axis and no Founder Score, so it could
    # never be screened or decided. Reuses the sourcing resolver, so an already-known founder
    # links to their existing record rather than forking a second one.
    if not extraction.founders:
        raise ValueError(
            f"deck for '{name}' names no founder: ArgOS is founder-first, so a deal cannot be "
            "opened without a person to attribute it to"
        )
    primary = extraction.founders[0]
    founder_id, _method = resolve_or_create_founder(
        db,
        {
            "display_name": primary.name,
            "occupation": primary.role,
            "current_company": name,
            "identity": {"linkedin": primary.linkedin},
            "status": "candidate",
        },
    )
    founder_name = primary.name

    # The application itself is the first signal — latency clock starts now.
    opp = Opportunity(
        id=opp_id,
        founder_id=founder_id,
        company_id=company.id,
        company_name=name,
        idea=extraction.idea,
        sector=extraction.sector,
        geo=extraction.geo,
        source="inbound",
        status="screening",
        first_signal_at=datetime.now(UTC),
    )
    db.add(opp)
    db.flush()

    # The founder provably belongs to this venture — record it, so the Founder Score can follow
    # them to whatever they build next.
    link_founder_company(db, founder_id, company.id)

    signal_by_page: dict[int, Signal] = {}
    for env in envelopes:
        sig, _created = upsert_signal(db, env)
        signal_by_page[env.raw["page"]] = sig
        db.execute(
            insert(founder_signal)
            .values(
                founder_id=founder_id,
                signal_id=sig.id,
                attribution_confidence=0.7,
                attribution_method="deck_primary_founder",
            )
            .on_conflict_do_nothing(index_elements=["founder_id", "signal_id"])
        )

    thesis = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    pre = hard_filter(thesis, extraction.sector) or prescreen_llm(_thesis_dict(thesis), pages)

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
                "founder": founder_name,
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
