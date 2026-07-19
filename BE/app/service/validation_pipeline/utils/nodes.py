"""Validation (processing) pipeline nodes — Graph 3, "the VC brain".

Uniform node contract (non-negotiable):

- signature ``def node(state: ProcessingState) -> dict`` — returned dict is a
  PARTIAL state update; LangGraph merges it via the reducers
- every node appends its own ``stage_timestamps`` entry AND a ``TraceEvent``
- stateless: everything a node knows comes from ``state`` or ``tools`` calls
- LLM calls always via ``with_structured_output(<pydantic model>)``

The three axis nodes run in PARALLEL (fan-out from ``hydrate``) and join at
``validator``; their outputs are merged by the ``merge_axis_dicts`` reducer —
merged as KEYS, never averaged (hard rule #1). ``idea_vs_market_axis`` must
never see the other axes' outputs, so no axis prompt includes ``axis_scores``.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any, Literal, cast

from app.service.models import (
    AxisScore,
    Decision,
    Memo,
    TraceEvent,
    TrustScore,
)
from app.service.tools import get_strong_llm
from app.service.validation_pipeline.utils import tools
from app.service.validation_pipeline.utils.models import (
    AxisScoreRecord,
    ContradictionRecord,
    DecisionRecord,
    MemoDraft,
    MemoRecord,
    ProcessingState,
    TraceRecord,
    ValidatorOutput,
)
from app.service.validation_pipeline.utils.prompts import (
    FOUNDER_AXIS_PROMPT,
    IDEA_VS_MARKET_AXIS_PROMPT,
    MARKET_AXIS_PROMPT,
    MEMO_WRITER_PROMPT,
    VALIDATOR_PROMPT,
)

STRONG_MODEL_NAME = "strong"  # logical route name (see service.tools.get_strong_llm)
REQUIRED_MEMO_SECTIONS = (
    "snapshot",
    "hypotheses",
    "swot",
    "problem_product",
    "traction",
)
_CITATION_RE = re.compile(r"\[((?:claim|sig)-[A-Za-z0-9\-]+)\]")


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _trace(
    state: ProcessingState,
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


def _evidence_block(state: ProcessingState) -> str:
    """Render signals + claims as the shared evidence block for axis prompts.
    Every line carries its id — the only ids the LLM is allowed to cite."""
    lines = ["SIGNALS (raw observations):"]
    lines += [
        f"- [{s.id}] source={s.source_type} url={s.source_url or '-'} payload={s.raw_payload}"
        for s in state.get("signals", [])
    ] or ["- (none)"]
    lines.append("\nCLAIMS (assertions extracted from the application):")
    lines += [
        f"- [{c.id}] ({c.category}, {c.source_pointer}"
        + (f", trust={c.trust.status}" if c.trust else ", trust=unassessed")
        + f") {c.text}"
        for c in state.get("claims", [])
    ] or ["- (none)"]
    return "\n".join(lines)


def _contradictions_block(state: ProcessingState) -> str:
    """On a validator retry, the disputed claims must be visible to the axes."""
    contradictions = state.get("contradictions", [])
    if not contradictions:
        return ""
    lines = [
        "\nDISPUTED CLAIMS from the previous validation round — re-score with "
        "these contradictions in mind:"
    ]
    lines += [
        f"- claim [{c.claim_id}] severity={c.severity}: {c.explanation} "
        f"(conflicting evidence: {c.conflicting_evidence_ids})"
        for c in contradictions
    ]
    return "\n".join(lines)


# --------------------------------- Nodes ----------------------------------- #


def hydrate(state: ProcessingState) -> dict[str, Any]:
    """
    Load founder history, signals, and claims by the ticket's ids from
    Memory and stamp ``processing_started``. The repository stub currently
    passes through what intake put in state; the real JOINs land with the
    Postgres run. No LLM.
    """
    started = _now()
    founder = state.get("founder")
    context = tools.load_ticket_context(
        {
            "opportunity_id": state.get("opportunity_id"),
            "founder_id": founder.id if founder else None,
        }
    )
    update: dict[str, Any] = {
        "validation_round": state.get("validation_round", 0),
        "contradictions": state.get("contradictions", []),
        "stage_timestamps": {"processing_started": _now()},
    }
    for key in ("founder", "signals", "claims"):
        if context.get(key):
            update[key] = context[key]

    update["trace"] = [
        _trace(
            state,
            "hydrate",
            started,
            rationale=(
                "Hydrated run context from Memory by the ticket's ids "
                f"({len(state.get('signals', []))} signal(s), "
                f"{len(state.get('claims', []))} claim(s) available); fanning out "
                "to the three independent axis agents in parallel."
            ),
            summary="context hydrated, processing started",
        )
    ]
    return update


def _score_axis(
    state: ProcessingState,
    axis: str,
    system_prompt: str,
    extra_context: str,
) -> dict[str, Any]:
    """
    Shared body of the three PARALLEL axis agents: strong LLM,
    ``with_structured_output(AxisScore)``. Each returns
    ``{"axis_scores": {axis: AxisScore}}`` — merged by key by the reducer,
    never averaged. None of them ever sees ``state["axis_scores"]``
    (independence, hard rule for idea_vs_market especially).
    """
    started = _now()
    thesis = state.get("thesis")
    prompt_input = (
        f"FUND THESIS: {thesis.model_dump() if thesis else '(not provided)'}\n\n"
        f"{_evidence_block(state)}"
        f"{extra_context}"
        f"{_contradictions_block(state)}"
    )
    score = cast(
        AxisScore,
        get_strong_llm()
        .with_structured_output(AxisScore)
        .invoke([("system", system_prompt), ("human", prompt_input)]),
    )
    # The schema allows any axis literal — pin it to this node's axis.
    score = score.model_copy(update={"axis": axis})

    trace = _trace(
        state,
        f"{axis}_axis",
        started,
        rationale=score.rationale,
        summary=(
            f"{axis} axis: score={score.score:.0f}, trend={score.trend}, "
            f"confidence={score.confidence:.2f}"
        ),
        model=STRONG_MODEL_NAME,
        evidence_ids=score.evidence_ids,
    )
    return {
        "axis_scores": {axis: score},
        "stage_timestamps": {f"axis_{axis}": _now()},
        "trace": [trace],
    }


def founder_axis(state: ProcessingState) -> dict[str, Any]:
    """
    Score WHO the person is. The persistent Founder Score history is ONE
    input, not a substitute. Mandatory cold-start path: no track record =>
    score from public-footprint proxies with confidence <= 0.5 and a
    rationale naming the missing evidence — never a silent zero.
    """
    founder = state.get("founder")
    history = tools.get_founder_history(founder.id) if founder else {}
    extra = (
        f"\n\nFOUNDER: {founder.model_dump() if founder else '(unresolved)'}\n"
        f"FOUNDER SCORE HISTORY (one input among several): {history}"
    )
    return _score_axis(state, "founder", FOUNDER_AXIS_PROMPT, extra)


def market_axis(state: ProcessingState) -> dict[str, Any]:
    """Score the MARKET: sizing sanity, competitor clusters, SWOT — all
    through the fund thesis lens."""
    company = state.get("company")
    extra = f"\n\nCOMPANY: {company.model_dump() if company else '(unresolved)'}"
    return _score_axis(state, "market", MARKET_AXIS_PROMPT, extra)


def idea_vs_market_axis(state: ProcessingState) -> dict[str, Any]:
    """Score the FIT: does the idea as-is survive scrutiny — and if not, is
    this team strong enough to pivot? Never reads the other axes' outputs."""
    company = state.get("company")
    founder = state.get("founder")
    extra = (
        f"\n\nCOMPANY: {company.model_dump() if company else '(unresolved)'}\n"
        f"FOUNDER (for the pivot-capability judgment only): "
        f"{founder.model_dump() if founder else '(unresolved)'}"
    )
    return _score_axis(state, "idea_vs_market", IDEA_VS_MARKET_AXIS_PROMPT, extra)


def validator(state: ProcessingState) -> dict[str, Any]:
    """
    Per-claim fact-check (fan-in point — waits for all three axes). For each
    claim: pick + run the external check via ``verify_claim_external``, then
    a strong-LLM adversarial pass assigns TrustScores and detects
    claim-vs-claim contradictions. Fetched evidence is appended as new
    Signals (nothing discarded). Increments ``validation_round``.
    """
    started = _now()
    claims = state.get("claims", [])
    signals = state.get("signals", [])
    round_n = state.get("validation_round", 0)

    fetched_signals = []
    verification_lines = []
    for claim in claims:
        result = tools.verify_claim_external(claim, signals)
        fetched_signals += result.get("fetched_signals", [])
        verification_lines.append(
            f"- claim [{claim.id}]: supporting={result['supporting_signal_ids']} "
            f"conflicting={result['conflicting_signal_ids']} notes={result['notes']}"
        )

    output = cast(
        ValidatorOutput,
        get_strong_llm()
        .with_structured_output(ValidatorOutput)
        .invoke(
            [
                ("system", VALIDATOR_PROMPT),
                (
                    "human",
                    f"{_evidence_block(state)}\n\nEXTERNAL VERIFICATION RESULTS:\n"
                    + ("\n".join(verification_lines) or "(no claims to verify)"),
                ),
            ]
        ),
    )

    verdicts = {v.claim_id: v for v in output.verdicts}
    updated_claims = []
    for claim in claims:
        verdict = verdicts.get(claim.id)
        trust = (
            TrustScore(
                confidence=verdict.confidence,
                status=verdict.status,
                evidence_ids=verdict.supporting_evidence_ids
                + verdict.conflicting_evidence_ids,
                contradiction_note=verdict.note or None,
            )
            if verdict
            # Graceful degradation: a claim the LLM skipped stays unverified.
            else TrustScore(
                confidence=0.0,
                status="unverified",
                contradiction_note="no verdict returned by validator",
            )
        )
        updated_claims.append(claim.model_copy(update={"trust": trust}))
        tools.update_claim_trust(claim.id, trust)

    tools.save_signals(fetched_signals)
    tools.save_contradictions(
        [
            ContradictionRecord(
                opportunity_id=state.get("opportunity_id", ""),
                claim_id=c.claim_id,
                conflicting_evidence_ids=c.conflicting_evidence_ids,
                explanation=c.explanation,
                severity=c.severity,
                detected_at=_now(),
            )
            for c in output.contradictions
        ]
    )

    statuses = [c.trust.status for c in updated_claims if c.trust]
    trace = _trace(
        state,
        "validator",
        started,
        rationale=output.rationale,
        summary=(
            f"round {round_n + 1}: {statuses.count('verified')} verified, "
            f"{statuses.count('unverified')} unverified, "
            f"{statuses.count('contradicted')} contradicted; "
            f"{len(output.contradictions)} contradiction(s) flagged"
        ),
        model=STRONG_MODEL_NAME,
        evidence_ids=[c.id for c in updated_claims],
    )
    return {
        "claims": updated_claims,
        "signals": fetched_signals,
        "contradictions": output.contradictions,
        "validation_round": round_n + 1,
        "stage_timestamps": {f"validated_round_{round_n + 1}": _now()},
        "trace": [trace],
    }


def memo_writer(state: ProcessingState) -> dict[str, Any]:
    """
    Generate the 5 required memo sections (strong LLM), then POST-VALIDATE
    IN CODE: (a) all required sections present, (b) every bracketed citation
    resolves to a real claim/signal id. Violations become explicit ``gaps``
    entries — never silently fixed. Attaches the LangSmith run id as
    ``trace_ref``.
    """
    started = _now()
    axis_scores = state.get("axis_scores", {})
    axes_block = "\n".join(
        f"- {axis}: score={s.score:.0f}, trend={s.trend}, confidence={s.confidence:.2f} "
        f"— {s.rationale}"
        for axis, s in axis_scores.items()
    )
    thesis = state.get("thesis")

    draft = cast(
        MemoDraft,
        get_strong_llm()
        .with_structured_output(MemoDraft)
        .invoke(
            [
                ("system", MEMO_WRITER_PROMPT),
                (
                    "human",
                    f"FUND THESIS: {thesis.model_dump() if thesis else '(not provided)'}\n\n"
                    f"THE THREE INDEPENDENT AXIS SCORES (never average them):\n{axes_block}\n\n"
                    f"CONTRADICTIONS FLAGGED: "
                    f"{[c.model_dump() for c in state.get('contradictions', [])]}\n\n"
                    f"{_evidence_block(state)}",
                ),
            ]
        ),
    )

    # Code post-validation (a): the 5 required sections.
    gaps = list(draft.gaps)
    sections = dict(draft.sections)
    for section in REQUIRED_MEMO_SECTIONS:
        if not sections.get(section, "").strip():
            sections[section] = (
                "Not disclosed — insufficient evidence to write this section."
            )
            gaps.append(f"Memo section '{section}': missing from generation")

    # Code post-validation (b): every citation resolves to a known id.
    known_ids = {c.id for c in state.get("claims", [])} | {
        s.id for s in state.get("signals", [])
    }
    cited = {m for text in sections.values() for m in _CITATION_RE.findall(text)}
    for bad_id in sorted(cited - known_ids):
        gaps.append(f"Citation [{bad_id}] does not resolve to a stored claim/signal")

    trace_ref = None
    try:
        from langsmith.run_helpers import get_current_run_tree

        run_tree = get_current_run_tree()
        trace_ref = str(run_tree.trace_id) if run_tree else None
    except Exception:  # tracing off / langsmith absent — never crash the run
        trace_ref = None

    memo = Memo(
        opportunity_id=state["opportunity_id"],
        sections=sections,
        gaps=gaps,
        recommendation=draft.recommendation,
        trace_ref=trace_ref,
    )
    tools.save_memo(
        MemoRecord(
            opportunity_id=memo.opportunity_id,
            sections=memo.sections,
            gaps=memo.gaps,
            recommendation=memo.recommendation,
            trace_ref=memo.trace_ref,
            created_at=_now(),
        )
    )

    trace = _trace(
        state,
        "memo_writer",
        started,
        rationale=(
            f"Memo drafted with recommendation '{memo.recommendation}'; "
            f"{len(cited)} citation(s) checked against {len(known_ids)} stored ids; "
            f"{len(gaps)} gap(s) flagged explicitly instead of fabricating."
        ),
        summary=f"memo ready, awaiting human decision (trace_ref={trace_ref})",
        model=STRONG_MODEL_NAME,
        evidence_ids=sorted(cited & known_ids),
    )
    return {
        "memo": memo,
        "stage_timestamps": {"memo_written": _now()},
        "trace": [trace],
    }


def decision_gate(state: ProcessingState) -> dict[str, Any]:
    """
    THE one human in the loop. The graph is compiled with
    ``interrupt_before=["decision_gate"]`` so execution halts before this
    node with full state checkpointed; ``resume_run`` injects the human
    ``Decision`` via ``update_state`` and resumes. This body only
    validates/normalizes the injected verdict.
    """
    started = _now()
    decision = state.get("decision")
    if decision is None:
        raise ValueError(
            "decision_gate resumed without a Decision in state — resume via "
            "validation_pipeline.agent.resume_run(opportunity_id, decision)"
        )
    decision = Decision.model_validate(decision)

    trace = _trace(
        state,
        "decision_gate",
        started,
        rationale=(
            f"Human {decision.human_id} decided '{decision.verdict}'"
            + (f": {decision.note}" if decision.note else "")
        ),
        summary=f"decision={decision.verdict}",
    )
    return {
        "decision": decision,
        "stage_timestamps": {"decided": _now()},
        "trace": [trace],
    }


def memory_writeback(state: ProcessingState) -> dict[str, Any]:
    """
    The ONLY node persisting conclusions: one transaction writes the human
    decision, the three independent axis scores, and the appended Founder
    Score point (append-only — the score never resets).
    """
    started = _now()
    decision = state.get("decision")
    axis_scores = state.get("axis_scores", {})
    founder = state.get("founder")
    opportunity_id = state["opportunity_id"]

    if decision is not None:
        founder_point = tools.compute_founder_score_point(founder, axis_scores)
        tools.finalize_opportunity(
            DecisionRecord(
                opportunity_id=opportunity_id,
                verdict=decision.verdict,
                human_id=decision.human_id,
                note=decision.note,
                decided_at=decision.decided_at,
            ),
            [
                AxisScoreRecord(
                    opportunity_id=opportunity_id,
                    axis=axis,
                    score=s.score,
                    trend=s.trend,
                    confidence=s.confidence,
                    rationale=s.rationale,
                    evidence_ids=s.evidence_ids,
                    validation_round=state.get("validation_round", 0),
                    scored_at=_now(),
                )
                for axis, s in axis_scores.items()
            ],
            founder_point,
        )

    trace = _trace(
        state,
        "memory_writeback",
        started,
        rationale=(
            "Persisted the human-gated conclusions in one transaction: decision, "
            f"{len(axis_scores)} axis score(s) (stored separately, never averaged), "
            "and the appended Founder Score point."
        ),
        summary=f"writeback complete for {opportunity_id}",
    )
    return {"stage_timestamps": {"written_back": _now()}, "trace": [trace]}


# ------------------- Routers (pure, no side effects) ----------------------- #


def route_validation(state: ProcessingState) -> Literal["retry", "ok"]:
    """
    After validator: severe contradictions AND validation_round < 2 =>
    "retry" (re-fan-out to the three axes with the disputed claims visible
    in state); else "ok" => memo_writer. Hard cap prevents infinite loops.
    """
    severe = any(c.severity == "high" for c in state.get("contradictions", []))
    if severe and state.get("validation_round", 0) < 2:
        return "retry"
    return "ok"
