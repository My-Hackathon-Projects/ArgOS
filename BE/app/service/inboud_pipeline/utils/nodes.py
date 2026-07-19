"""Inbound pipeline nodes — Graph 1 (sourcing + screening of an applicant).

Uniform node contract (non-negotiable):

- signature ``def node(state: InboundState) -> dict`` — returned dict is a
  PARTIAL state update; LangGraph merges it via the reducers
- every node appends its own ``stage_timestamps`` entry (time-to-decision is
  a graded criterion) AND a ``TraceEvent`` (rationale trail, persisted later)
- stateless: everything a node knows comes from ``state`` or ``tools`` calls
- LLM calls always via ``with_structured_output(<pydantic model>)``
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.core.storage import upload_blob
from app.service.inboud_pipeline.utils import tools
from app.service.inboud_pipeline.utils.models import (
    ClaimExtraction,
    ClaimRecord,
    CompanyRecord,
    FounderRecord,
    InboundState,
    OpportunityRecord,
    RejectionRecord,
    SignalRecord,
    TraceRecord,
)
from app.service.inboud_pipeline.utils.prompts import (
    EXTRACT_CLAIMS_PROMPT,
    PRE_SCREEN_PROMPT,
)
from app.service.models import (
    Claim,
    Company,
    Founder,
    PreScreenResult,
    ProcessingTicket,
    Thesis,
    TraceEvent,
)
from app.service.tools import get_fast_llm

FAST_MODEL_NAME = "fast"  # logical route name (see service.tools.get_fast_llm)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _trace(
    state: InboundState,
    node: str,
    started_at: str,
    rationale: str,
    summary: str,
    model: str | None = None,
    evidence_ids: list[str] | None = None,
) -> TraceEvent:
    """Build the node's TraceEvent and persist it (append-only traces table)."""
    ended_at = _now()
    duration_ms = (
        datetime.fromisoformat(ended_at) - datetime.fromisoformat(started_at)
    ).total_seconds() * 1000
    event = TraceEvent(
        id=f"trace-{uuid.uuid4().hex[:12]}",
        opportunity_id=state.get("opportunity_id", ""),
        node=node,
        started_at=started_at,
        ended_at=ended_at,
        duration_ms=duration_ms,
        model=model,
        rationale=rationale,
        summary=summary,
        evidence_ids=evidence_ids or [],
    )
    tools.save_trace_events([TraceRecord(**event.model_dump())])
    return event


def _deck_pages(state: InboundState) -> str:
    """Render deck-page signals as the LLM input block, page numbers included."""
    pages = [
        f"[deck p.{s.raw_payload.get('page')}] (signal_id={s.id})\n{s.raw_payload.get('text', '')}"
        for s in state.get("signals", [])
        if s.source_type == "deck"
    ]
    return "\n\n".join(pages) or "(no deck content)"


# --------------------------------- Nodes ----------------------------------- #


def ingest_deck(state: InboundState) -> dict[str, Any]:
    """
    Parse the uploaded deck into per-page Signals (+ one application-form
    Signal) and persist them append-only. The raw PDF itself goes to blob
    storage under ``decks/{opportunity_id}.pdf`` (key stored on the
    opportunity row). Deterministic content-hash ids make re-uploads
    idempotent. Minimum inbound application = company name + deck PDF —
    nothing more is required (hard rule #9).
    """
    started = _now()
    raw_deck = state.get("raw_deck")
    company_name = state.get("company_name", "Unknown")

    blob_key: str | None = None
    if raw_deck:
        blob_key = f"decks/{state.get('opportunity_id', 'unknown')}.pdf"
        upload_blob(blob_key, raw_deck, content_type="application/pdf")
        tools.set_deck_blob_key(state.get("opportunity_id", ""), blob_key)

    signals = tools.parse_deck_pdf(raw_deck, company_name) if raw_deck else []
    tools.save_signals(
        [
            SignalRecord(**s.model_dump(), opportunity_id=state.get("opportunity_id"))
            for s in signals
        ]
    )

    n_pages = sum(1 for s in signals if s.source_type == "deck")
    trace = _trace(
        state,
        "ingest_deck",
        started,
        rationale=(
            f"Extracted {n_pages} deck page(s) with pymupdf; page numbers preserved "
            "as source pointers so every downstream claim stays citable. "
            "Content-hash signal ids keep re-uploads idempotent."
            if signals
            else "No deck bytes provided; proceeding with whatever signals are in state."
        ),
        summary=f"{len(signals)} signal(s) ingested for '{company_name}'",
        evidence_ids=[s.id for s in signals],
    )
    return {
        "signals": signals,
        "stage_timestamps": {"ingested": _now()},
        "trace": [trace],
    }


def resolve_entities(state: InboundState) -> dict[str, Any]:
    """
    Entity resolution + dedup: exact handle match -> fuzzy name -> pgvector
    similarity via the repository. On a match, MERGE into the canonical
    Founder so the Founder Score history carries over; otherwise create new
    entities with deterministic ids (same company re-applying resolves to
    the same rows).
    """
    started = _now()
    hints = sorted({h for s in state.get("signals", []) for h in s.entity_hints})
    company_name = state.get("company_name", "Unknown")

    matched = tools.find_matching_founder(hints)
    if matched is not None:
        founder = matched
        decision = (
            f"Matched entity hints {hints} to canonical founder '{founder.canonical_name}' "
            f"({founder.id}) — merging so their Founder Score history carries over."
        )
    else:
        founder_key = hashlib.sha256(
            (hints[0] if hints else company_name).encode()
        ).hexdigest()[:12]
        founder = Founder(
            id=f"founder-{founder_key}",
            canonical_name=hints[0] if hints else "Unknown",
        )
        decision = (
            f"No canonical founder matched hints {hints} (exact handle, fuzzy name, "
            "vector similarity all missed) — created a new canonical entity."
        )

    company_key = hashlib.sha256(company_name.lower().encode()).hexdigest()[:12]
    company = Company(
        id=f"company-{company_key}", name=company_name, founder_ids=[founder.id]
    )
    founder, company = tools.upsert_entities(
        FounderRecord(**founder.model_dump(exclude={"score_history"})),
        CompanyRecord(**company.model_dump()),
    )

    trace = _trace(
        state,
        "resolve_entities",
        started,
        rationale=decision,
        summary=f"founder={founder.id}, company={company.id}",
    )
    return {
        "founder": founder,
        "company": company,
        "stage_timestamps": {"resolved": _now()},
        "trace": [trace],
    }


def extract_claims(state: InboundState) -> dict[str, Any]:
    """
    TERMINAL node. Structured extraction of checkable Claims from the deck
    pages (fast LLM, ``with_structured_output(ClaimExtraction)``). Claims
    are born with ``trust=None`` — the validation pipeline assigns
    TrustScores. Ids are deterministic content hashes (idempotent re-runs).

    Inserting the claim batch is the final act of this graph: right after
    ``save_claims`` the node builds the §5 ``ProcessingTicket``, upserts the
    Opportunity row (stage="queued"), and hands off via
    ``enqueue_processing`` — every claim batch inserted from the inbound
    pipeline triggers the validation pipeline. An empty batch still hands
    off (validation judges from signals; stranding the opportunity would
    be worse than an empty claim set).
    """
    started = _now()
    company = state.get("company")
    company_id = company.id if company else "company-unknown"

    extraction = cast(
        ClaimExtraction,
        get_fast_llm()
        .with_structured_output(ClaimExtraction)
        .invoke(
            [
                ("system", EXTRACT_CLAIMS_PROMPT),
                ("human", f"Deck pages:\n\n{_deck_pages(state)}"),
            ]
        ),
    )

    claims = [
        Claim(
            id=f"claim-{hashlib.sha256(f'{company_id}:{c.text}'.encode()).hexdigest()[:12]}",
            company_id=company_id,
            category=c.category,
            text=c.text,
            source_pointer=c.source_pointer,
            trust=None,
        )
        for c in extraction.claims
    ]
    tools.save_claims(
        [
            ClaimRecord(
                id=c.id,
                opportunity_id=state.get("opportunity_id", ""),
                company_id=c.company_id,
                category=c.category,
                text=c.text,
                source_pointer=c.source_pointer,
            )
            for c in claims
        ]
    )

    # Claims are inserted — hand off to the validation pipeline (§5 ticket).
    founder = state.get("founder")
    thesis = state.get("thesis")
    ticket = ProcessingTicket(
        opportunity_id=state["opportunity_id"],
        track="inbound",
        thesis=thesis if thesis is not None else Thesis(),
        founder_id=founder.id if founder else "",
        company_id=company.id if company else "",
        signal_ids=[s.id for s in state.get("signals", [])],
        claim_ids=[c.id for c in claims],
        handoff_at=_now(),
    )
    tools.save_opportunity(
        OpportunityRecord(
            opportunity_id=ticket.opportunity_id,
            track="inbound",
            company_id=ticket.company_id,
            founder_id=ticket.founder_id,
            stage="queued",
            thesis_json=ticket.thesis.model_dump(),
            created_at=state.get("stage_timestamps", {}).get("ingested", started),
            updated_at=_now(),
        )
    )
    tools.enqueue_processing(ticket)

    trace = _trace(
        state,
        "extract_claims",
        started,
        rationale=(
            f"{extraction.rationale} Claim batch inserted; handed "
            f"{len(ticket.signal_ids)} signal(s) / {len(ticket.claim_ids)} claim(s) "
            "to the validation pipeline on thread_id=opportunity_id."
        ),
        summary=f"{len(claims)} claim(s) inserted, trust=None; ticket emitted",
        model=FAST_MODEL_NAME,
        evidence_ids=[c.id for c in claims],
    )
    return {
        "claims": claims,
        "ticket": ticket,
        "stage_timestamps": {"claims_extracted": _now(), "ticket_emitted": _now()},
        "trace": [trace],
    }


def pre_screen(state: InboundState) -> dict[str, Any]:
    """
    Cheap kill-filter, two stages:
      (a) deterministic thesis hard filters (sector/geo/stage) in CODE —
          a hard-filter miss rejects without spending an LLM call;
      (b) one fast-LLM viability check (uncertain => PASS, per prompt).
    Rejections carry a reason and are logged — never silently dropped; the
    signals stay in Memory and still feed the Founder Score.
    """
    started = _now()
    thesis = state.get("thesis")
    company = state.get("company")

    result: PreScreenResult | None = None
    stage_used = "code hard filters"
    if thesis and company:
        for attr, allowed in (
            ("sector", thesis.sectors),
            ("geo", thesis.geographies),
            ("stage", thesis.stages),
        ):
            value = getattr(company, attr)
            if allowed and value and value not in allowed:
                result = PreScreenResult(
                    verdict="reject",
                    reason=f"Thesis hard filter: {attr}='{value}' not in {allowed}",
                )
                break

    if result is None:
        stage_used = "fast-LLM viability check"
        thesis_json = thesis.model_dump() if thesis else {}
        result = cast(
            PreScreenResult,
            get_fast_llm()
            .with_structured_output(PreScreenResult)
            .invoke(
                [
                    ("system", PRE_SCREEN_PROMPT),
                    (
                        "human",
                        f"Thesis: {thesis_json}\n\nApplication content:\n\n{_deck_pages(state)}",
                    ),
                ]
            ),
        )

    if result.verdict == "reject":
        tools.log_rejection(
            RejectionRecord(
                opportunity_id=state.get("opportunity_id", ""),
                reason=result.reason,
                rejected_at=_now(),
            )
        )
        # The funnel row must reflect the outcome — reject ends the graph.
        tools.update_opportunity_stage(state.get("opportunity_id", ""), "rejected")

    trace = _trace(
        state,
        "pre_screen",
        started,
        rationale=f"Verdict '{result.verdict}' from {stage_used}: {result.reason}",
        summary=f"prescreen={result.verdict}",
        model=FAST_MODEL_NAME if stage_used.startswith("fast") else None,
    )
    return {
        "prescreen": result,
        "stage_timestamps": {"prescreened": _now()},
        "trace": [trace],
    }


# ------------------- Routers (pure, no side effects) ----------------------- #


def route_prescreen(state: InboundState) -> Literal["pass", "reject"]:
    """pass -> extract_claims; reject -> END (rejection already logged by the node)."""
    prescreen = state.get("prescreen")
    return prescreen.verdict if prescreen else "pass"
