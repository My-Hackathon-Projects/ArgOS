"""Inbound pipeline tools — deck parsing + Postgres repository + handoff.

Trust boundary rule: anything from outside enters the system only as a
``Signal`` (raw_payload preserved). Nodes never write SQL — all Memory access
goes through the repository functions below. Each function's docstring names
the target Postgres table and the record model (see ``models.py``) that
defines its exact attributes.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import Session, col, select

from app import models as db
from app.core.db import engine
from app.service.inboud_pipeline.utils.models import (
    ClaimRecord,
    CompanyRecord,
    FounderRecord,
    OpportunityRecord,
    OpportunityStage,
    RejectionRecord,
    SignalRecord,
    TraceRecord,
)
from app.service.models import Company, Founder, ProcessingTicket, Signal

# ------------------------------ Deck parsing ------------------------------ #


def parse_deck_pdf(pdf_bytes: bytes, company_name: str) -> list[Signal]:
    """
    Turn an uploaded pitch deck into Signals: one Signal per page (pymupdf
    text extraction, page number preserved — ``source_pointer="deck p.N"``
    downstream depends on it) plus one application-form Signal carrying the
    submitted company name. Signal ids are deterministic content hashes so
    re-uploading the same deck cannot duplicate signals (idempotency).
    No interpretation here — claim extraction is a node, not a tool.
    """
    import fitz  # type: ignore[import-untyped]  # pymupdf

    now = datetime.now(UTC).isoformat()
    signals: list[Signal] = []

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_index, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            digest = hashlib.sha256(
                f"{company_name}:deck:{page_index}:{text}".encode()
            ).hexdigest()[:16]
            signals.append(
                Signal(
                    id=f"sig-deck-{digest}",
                    source_type="deck",
                    source_url=None,
                    raw_payload={"page": page_index, "text": text},
                    entity_hints=[company_name],
                    fetched_at=now,
                )
            )

    form_digest = hashlib.sha256(f"{company_name}:application".encode()).hexdigest()[
        :16
    ]
    signals.append(
        Signal(
            id=f"sig-app-{form_digest}",
            source_type="application",
            source_url=None,
            raw_payload={"company_name": company_name},
            entity_hints=[company_name],
            fetched_at=now,
        )
    )
    return signals


# --------------------------- Repository (Memory) --------------------------- #


def save_signals(signals: list[SignalRecord]) -> None:
    """
    Append-only INSERT into ``signals`` (attributes: SignalRecord).
    Idempotent: INSERT ... ON CONFLICT (id) DO NOTHING — ids are content
    hashes, so re-uploads no-op. Never UPDATE, never DELETE.
    """
    if not signals:
        return
    with Session(engine) as session:
        session.execute(
            insert(db.Signal)
            .values([s.model_dump() for s in signals])
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.commit()


def find_matching_founder(entity_hints: list[str]) -> Founder | None:
    """
    Entity resolution lookup against ``founders``: exact canonical_name
    match against the hints. Returns the canonical Founder (so score
    history carries over) or None.
    """
    # TODO: fuzzy canonical_name + pgvector similarity on profile text.
    if not entity_hints:
        return None
    with Session(engine) as session:
        row = session.exec(
            select(db.Founder).where(col(db.Founder.canonical_name).in_(entity_hints))
        ).first()
        if row is None:
            return None
        return Founder.model_validate(row.model_dump())


def upsert_entities(
    founder: FounderRecord, company: CompanyRecord
) -> tuple[Founder, Company]:
    """
    Upsert into ``founders`` / ``companies`` (attributes: FounderRecord /
    CompanyRecord). On conflict the existing ``founder_score`` and
    ``score_history`` are kept — the Founder Score persists forever, never
    resets. Returns the canonical domain entities as stored.
    """
    with Session(engine) as session:
        founder_stmt = insert(db.Founder).values(founder.model_dump())
        session.execute(
            founder_stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "canonical_name": founder_stmt.excluded.canonical_name,
                    "handles": founder_stmt.excluded.handles,
                    "education": founder_stmt.excluded.education,
                    # founder_score / score_history intentionally NOT set —
                    # the canonical row's score survives re-applications.
                },
            )
        )
        company_stmt = insert(db.Company).values(company.model_dump())
        session.execute(
            company_stmt.on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "name": company_stmt.excluded.name,
                    "founder_ids": company_stmt.excluded.founder_ids,
                    "sector": company_stmt.excluded.sector,
                    "geo": company_stmt.excluded.geo,
                    "stage": company_stmt.excluded.stage,
                },
            )
        )
        session.commit()
        founder_row = session.get(db.Founder, founder.id)
        company_row = session.get(db.Company, company.id)
        assert founder_row is not None and company_row is not None
        return (
            Founder.model_validate(founder_row.model_dump()),
            Company.model_validate(company_row.model_dump()),
        )


def save_claims(claims: list[ClaimRecord]) -> None:
    """
    INSERT into ``claims`` (attributes: ClaimRecord). trust_* columns are
    NULL here; the validation pipeline UPDATEs them later. Idempotent on
    the content-hash id.
    """
    if not claims:
        return
    with Session(engine) as session:
        session.execute(
            insert(db.Claim)
            .values([c.model_dump() for c in claims])
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.commit()


def log_rejection(rejection: RejectionRecord) -> None:
    """
    Upsert into ``rejections`` (attributes: RejectionRecord). Rejected !=
    deleted: the opportunity's signals stay in Memory and still feed the
    Founder Score.
    """
    with Session(engine) as session:
        stmt = insert(db.Rejection).values(rejection.model_dump())
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["opportunity_id"],
                set_={
                    "reason": stmt.excluded.reason,
                    "rejected_at": stmt.excluded.rejected_at,
                },
            )
        )
        session.commit()


def save_opportunity(opportunity: OpportunityRecord) -> None:
    """
    Upsert into ``opportunities`` (attributes: OpportunityRecord) — the
    funnel row whose ``stage`` transitions received -> queued (or rejected).
    ``created_at`` is kept from the first insert; ``deck_blob_key`` is only
    overwritten when the new value is non-null.
    """
    with Session(engine) as session:
        stmt = insert(db.Opportunity).values(opportunity.model_dump())
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["opportunity_id"],
                set_={
                    "track": stmt.excluded.track,
                    "company_id": stmt.excluded.company_id,
                    "founder_id": stmt.excluded.founder_id,
                    "stage": stmt.excluded.stage,
                    "thesis_json": stmt.excluded.thesis_json,
                    "deck_blob_key": func.coalesce(
                        stmt.excluded.deck_blob_key, db.Opportunity.deck_blob_key
                    ),
                    "updated_at": stmt.excluded.updated_at,
                },
            )
        )
        session.commit()


def update_opportunity_stage(opportunity_id: str, stage: OpportunityStage) -> None:
    """Move the funnel row to a new stage (e.g. pre-screen reject)."""
    if not opportunity_id:
        return
    with Session(engine) as session:
        row = session.get(db.Opportunity, opportunity_id)
        if row is None:
            return
        row.stage = stage
        row.updated_at = datetime.now(UTC).isoformat()
        session.add(row)
        session.commit()


def set_deck_blob_key(opportunity_id: str, blob_key: str) -> None:
    """Record where the raw deck PDF lives in blob storage."""
    if not opportunity_id:
        return
    with Session(engine) as session:
        row = session.get(db.Opportunity, opportunity_id)
        if row is None:
            return
        row.deck_blob_key = blob_key
        row.updated_at = datetime.now(UTC).isoformat()
        session.add(row)
        session.commit()


def save_trace_events(traces: list[TraceRecord]) -> None:
    """
    Append-only INSERT into ``traces`` (attributes: TraceRecord) — the
    persisted per-node reasoning trail behind the UI "show reasoning" panel.
    """
    if not traces:
        return
    with Session(engine) as session:
        session.execute(
            insert(db.Trace)
            .values([t.model_dump() for t in traces])
            .on_conflict_do_nothing(index_elements=["id"])
        )
        session.commit()


# --------------------------------- Handoff --------------------------------- #


def enqueue_processing(ticket: ProcessingTicket) -> None:
    """
    §5 handoff: hand the ticket to the validation (processing) graph on
    ``thread_id == opportunity_id``. Kept behind this one helper so it can
    be swapped for a real queue later without touching graph code. Lazy
    import avoids a circular dependency at module load.
    """
    from app.service.validation_pipeline import agent as validation_agent

    validation_agent.graph.invoke(
        validation_agent.ticket_to_state(ticket),
        config={"configurable": {"thread_id": ticket.opportunity_id}},
    )
