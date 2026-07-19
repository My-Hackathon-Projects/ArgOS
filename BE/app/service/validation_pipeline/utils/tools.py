# Repository signatures are final; SQL/HTTP bodies land in a later run — their
# args are intentionally unused for now.
# ruff: noqa: ARG001
"""Validation (processing) pipeline tools — external fact-checking + repository stubs.

Trust boundary rule: external verification results enter the system only as
``Signal``s (raw_payload preserved) and are cited later via evidence_ids.
Nodes never write SQL — all Memory access goes through the repository
functions below. Each stub's docstring names the target Postgres table and
the record model (see ``models.py``) defining its exact attributes.
"""

from __future__ import annotations

from typing import Any

from app.service.models import Claim, Founder, Signal, TrustScore
from app.service.validation_pipeline.utils.models import (
    AxisScoreRecord,
    ContradictionRecord,
    DecisionRecord,
    FounderScorePointRecord,
    MemoRecord,
    TraceRecord,
)

# ------------------------- External fact-checking -------------------------- #


def verify_claim_external(claim: Claim, signals: list[Signal]) -> dict[str, Any]:
    """
    The validator's fact-checking tool. Given a Claim, decide which external
    check applies (GitHub stars -> GitHub API, "launched on HN" -> HN Algolia
    search, papers -> arXiv), run it, and return
    ``{"supporting_signal_ids": [...], "conflicting_signal_ids": [...],
    "fetched_signals": [Signal, ...], "notes": str}``.

    Fetched evidence is returned as new Signals so the caller appends them to
    state (nothing discarded). Graceful degradation is mandatory: an API
    failure returns empty evidence + a note — the claim then stays
    ``unverified``, a run never crashes on a rate limit.
    """
    # TODO(HTTP run): route by claim.category -> httpx GitHub/HN/arXiv, diff
    # the fetched numbers against the claim text.
    return {
        "supporting_signal_ids": [],
        "conflicting_signal_ids": [],
        "fetched_signals": [],
        "notes": "external verification not yet wired; treating as unverified",
    }


# ------------------------- Repository (Memory) stubs ----------------------- #


def load_ticket_context(ticket_like: dict[str, Any]) -> dict[str, Any]:
    """
    Hydration query for ``hydrate``: given the ticket's ids, load the
    canonical Founder (with full score_history), the Signals in
    ``signal_ids``, and the Claims in ``claim_ids`` from Memory. Returns
    ``{"founder": ..., "signals": [...], "claims": [...],
    "founder_history": {...}}``. Stub passes through what intake put in
    state; the real JOINs land with the Postgres run.
    """
    # TODO(postgres run): SELECT founders/signals/claims by id + score_history.
    return {}


def get_founder_history(founder_id: str) -> dict[str, Any]:
    """
    Everything Memory knows about a person: past signals, past opportunities
    and decisions, and the full founder score_history. ONE input to the
    founder axis — never a substitute for it.
    """
    # TODO(postgres run): join signals + opportunities + decisions + points.
    return {"signals": [], "opportunities": [], "score_history": []}


def update_claim_trust(claim_id: str, trust: TrustScore) -> None:
    """
    UPDATE ``claims`` SET trust_status/trust_confidence/evidence_ids
    (attributes: see inbound ClaimRecord) — the only mutation claims ever
    receive; the rows themselves are never deleted.
    """
    # TODO(postgres run): real UPDATE.
    return None


def save_axis_scores(records: list[AxisScoreRecord]) -> None:
    """INSERT into ``axis_scores`` (attributes: AxisScoreRecord). Three
    independent rows per round — never a combined/averaged column."""
    # TODO(postgres run): real INSERT.
    return None


def save_contradictions(records: list[ContradictionRecord]) -> None:
    """Append-only INSERT into ``contradictions`` (attributes: ContradictionRecord)."""
    # TODO(postgres run): real INSERT.
    return None


def save_signals(signals: list[Signal]) -> None:
    """Append-only INSERT into ``signals`` for validator-fetched evidence.
    Same INSERT-only table the inbound pipeline writes."""
    # TODO(postgres run): INSERT ... ON CONFLICT DO NOTHING.
    return None


def save_memo(memo: MemoRecord) -> None:
    """INSERT into ``memos`` (attributes: MemoRecord — sections/gaps jsonb,
    trace_ref = LangSmith run id for the "show reasoning" panel)."""
    # TODO(postgres run): real INSERT.
    return None


def save_trace_events(traces: list[TraceRecord]) -> None:
    """Append-only INSERT into ``traces`` (attributes: TraceRecord)."""
    # TODO(postgres run): real INSERT.
    return None


def finalize_opportunity(
    decision: DecisionRecord,
    axis_scores: list[AxisScoreRecord],
    founder_point: FounderScorePointRecord | None,
) -> None:
    """
    The writeback node's SINGLE transaction: persist the human decision
    (``decisions``), the three axis scores (``axis_scores``), append the new
    Founder Score point (``founder_score_points`` — append-only, never
    reset), and stamp ``opportunities.updated_at``. Invariant: domain tables
    hold only human-gated conclusions; provisional state lives in
    checkpoints.
    """
    # TODO(postgres run): one transaction over the four tables above.
    return None


def compute_founder_score_point(
    founder: Founder | None, axis_scores: dict[str, Any]
) -> FounderScorePointRecord | None:
    """
    Derive the new appended Founder Score point from the founder-axis score
    of this run. Pure helper (no IO) so the writeback transaction stays one
    call. Returns None when there is no founder or no founder-axis score.
    """
    from datetime import UTC, datetime

    founder_axis = axis_scores.get("founder")
    if founder is None or founder_axis is None:
        return None
    return FounderScorePointRecord(
        founder_id=founder.id,
        timestamp=datetime.now(UTC).isoformat(),
        value=founder_axis.score,
        trigger_signal_id=(founder_axis.evidence_ids or [None])[0],
    )
