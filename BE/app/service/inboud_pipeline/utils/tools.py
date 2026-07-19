# Repository signatures are final; SQL bodies land in a later run — their args
# are intentionally unused for now.
# ruff: noqa: ARG001
"""Inbound pipeline tools — deck parsing (real) + repository stubs + handoff.

Trust boundary rule: anything from outside enters the system only as a
``Signal`` (raw_payload preserved). Nodes never write SQL — all Memory access
goes through the repository functions below. Each stub's docstring names the
target Postgres table and the record model (see ``models.py``) that defines
its exact attributes; the real SQL implementation drops in behind these
signatures in a later run.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

from app.service.inboud_pipeline.utils.models import (
    ClaimRecord,
    CompanyRecord,
    FounderRecord,
    OpportunityRecord,
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
    import fitz  # pymupdf

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


# ------------------------- Repository (Memory) stubs ----------------------- #


def save_signals(signals: list[SignalRecord]) -> None:
    """
    Append-only INSERT into ``signals`` (attributes: SignalRecord).
    Idempotent: INSERT ... ON CONFLICT (id) DO NOTHING — ids are content
    hashes, so re-uploads no-op. Never UPDATE, never DELETE.
    """
    # TODO(postgres run): INSERT ... ON CONFLICT DO NOTHING via app.core.db.
    return None


def find_matching_founder(entity_hints: list[str]) -> Founder | None:
    """
    Entity resolution lookup against ``founders``: exact handle match first,
    then fuzzy canonical_name, then pgvector similarity on profile text.
    Returns the canonical Founder (so score history carries over) or None.
    """
    # TODO(postgres run): exact-handle SQL -> fuzzy -> pgvector.
    return None


def upsert_entities(
    founder: FounderRecord, company: CompanyRecord
) -> tuple[Founder, Company]:
    """
    Upsert into ``founders`` / ``companies`` (attributes: FounderRecord /
    CompanyRecord). On a resolution match, MERGE into the canonical founder
    row — founder_score and score_history persist forever, never reset.
    Returns the canonical domain entities.
    """
    # TODO(postgres run): real upsert; for now echo back as domain models.
    return (
        Founder(
            id=founder.id,
            canonical_name=founder.canonical_name,
            handles=founder.handles,
            education=founder.education,
            founder_score=founder.founder_score,
        ),
        Company(
            id=company.id,
            name=company.name,
            founder_ids=company.founder_ids,
            sector=company.sector,
            geo=company.geo,
            stage=company.stage,
        ),
    )


def save_claims(claims: list[ClaimRecord]) -> None:
    """
    INSERT into ``claims`` (attributes: ClaimRecord). trust_* columns are
    NULL here; the validation pipeline UPDATEs them later.
    """
    # TODO(postgres run): real INSERT.
    return None


def log_rejection(rejection: RejectionRecord) -> None:
    """
    INSERT into ``rejections`` (attributes: RejectionRecord). Rejected !=
    deleted: the opportunity's signals stay in Memory and still feed the
    Founder Score.
    """
    # TODO(postgres run): real INSERT.
    return None


def save_opportunity(opportunity: OpportunityRecord) -> None:
    """
    Upsert into ``opportunities`` (attributes: OpportunityRecord) — the
    funnel row whose ``stage`` transitions screened -> queued (or rejected).
    """
    # TODO(postgres run): INSERT ... ON CONFLICT (opportunity_id) DO UPDATE.
    return None


def save_trace_events(traces: list[TraceRecord]) -> None:
    """
    Append-only INSERT into ``traces`` (attributes: TraceRecord) — the
    persisted per-node reasoning trail behind the UI "show reasoning" panel.
    """
    # TODO(postgres run): real INSERT.
    return None


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
