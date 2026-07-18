"""nodes.py — the Intelligence layer.

Every function here **is** a LangGraph node. Uniform node contract
(non-negotiable):

- signature: ``def node(state: GraphState) -> dict`` — the returned dict is a
  **partial** state update; LangGraph merges it
- every node appends its own entry to ``stage_timestamps`` (time-to-decision is
  a graded criterion)
- stateless: everything a node knows comes from ``state`` or ``tools.py`` calls
  — never module-level mutable state (checkpoint/resume safety)
- LLM calls always via ``with_structured_output(<pydantic model>)``

STATUS: skeleton pass. Bodies return minimal dummy updates so the graph runs
end-to-end on seed data. Each docstring is the implementation ticket.
"""

from __future__ import annotations

from datetime import UTC, datetime

from app.service import tools
from app.service.models import (
    AxisScore,
    Claim,
    Company,
    Founder,
    GraphState,
    Memo,
    PreScreenResult,
    Signal,
)


def _stamp(stage: str) -> dict[str, str]:
    """One-line helper: {stage: now-iso} for the stage_timestamps reducer."""
    return {stage: datetime.now(UTC).isoformat()}


# --------------------------------- Intake ---------------------------------


def ingest(state: GraphState) -> dict:
    """
    Entry node for BOTH tracks (inbound deck / outbound scan converge here
    — one funnel, per brief).
      - inbound: parse_deck_pdf() -> Signals
      - outbound: Signals already collected by the scanner sub-graph are
        passed in through state
    Writes: save_signals() (append-only).
    Returns: {"signals": [...], "stage_timestamps": {...}}.
    """
    signals: list[Signal] = state.get("signals") or tools.load_seed_signals()
    tools.save_signals(signals)
    return {"signals": signals, "stage_timestamps": _stamp("ingested")}


def resolve_entities(state: GraphState) -> dict:
    """
    Entity resolution + dedup (FR-2.3). Use entity_hints from signals with
    find_matching_founder(); on match, MERGE into the canonical Founder so
    their Founder Score history carries over; else create new entities.
    Writes: upsert_entities().
    Returns: {"founder": ..., "company": ...}.
    """
    hints = [h for s in state.get("signals", []) for h in s.entity_hints]
    founder = tools.find_matching_founder(hints) or Founder(
        id="founder-stub", canonical_name=(hints[0] if hints else "Unknown")
    )
    company = Company(id="company-stub", name="Stub Co", founder_ids=[founder.id])
    founder, company = tools.upsert_entities(founder, company)
    return {
        "founder": founder,
        "company": company,
        "stage_timestamps": _stamp("resolved"),
    }


def extract_claims(state: GraphState) -> dict:
    """
    Turn deck/application signals into structured Claims via fast LLM with
    structured output. Each claim must carry a precise source_pointer
    ("deck p.4") — the memo's clickable citations depend on it. Claims are
    born with trust=None (validator fills it).
    Writes: save_claims().
    Returns: {"claims": [...]}.
    """
    company = state.get("company")
    company_id = company.id if company else "company-stub"
    claims = [
        Claim(
            id="claim-stub-1",
            company_id=company_id,
            category="traction",
            text="12K GitHub stars",
            source_pointer="deck p.4",
        )
    ]
    tools.save_claims(claims)
    return {"claims": claims, "stage_timestamps": _stamp("claims_extracted")}


def pre_screen(state: GraphState) -> dict:
    """
    Fast, CHEAP first-pass filter (FR-3.3): kill clearly non-viable ideas
    before expensive analysis. Checks: thesis hard filters (sector/geo/
    stage) + a one-shot fast-LLM viability sniff. Rejections carry a
    reason and are logged (log_rejection), never silently dropped.
    Returns: {"prescreen": PreScreenResult(...)}.
    """
    result = PreScreenResult(verdict="pass", reason="stub: passes all filters")
    if result.verdict == "reject":
        tools.log_rejection(state["opportunity_id"], result.reason)
    return {"prescreen": result, "stage_timestamps": _stamp("prescreened")}


# ----- The three axis agents — PARALLEL, merged by reducer, NEVER averaged -----


def founder_axis(state: GraphState) -> dict:
    """
    Score WHO the person is. Inputs: get_founder_history() (the persistent
    Founder Score is ONE input here, not a substitute — brief FAQ #6),
    signals, claims. MUST implement the explicit cold-start path (FR-9):
    with no track record, score from public-footprint proxies (domain
    expertise in writing, shipping velocity of whatever exists,
    application quality) and return LOW confidence — honest uncertainty,
    never a silent zero. Strong LLM, structured output AxisScore.
    Returns: {"axis_scores": {"founder": AxisScore}}.
    """
    founder = state.get("founder")
    _history = tools.get_founder_history(founder.id) if founder else {}
    score = AxisScore(
        axis="founder",
        score=60.0,
        trend="stable",
        rationale="stub founder rationale",
        confidence=0.4,  # honest low confidence for cold-start (FR-9)
    )
    return {
        "axis_scores": {"founder": score},
        "stage_timestamps": _stamp("axis_founder"),
    }


def market_axis(state: GraphState) -> dict:  # noqa: ARG001  (stub: state used once real)
    """
    Score the MARKET: sizing sanity check, competitor clusters, SWOT;
    verdict expressed as bullish/neutral/bear via the score + rationale.
    Weighted through the Thesis (a great market outside the fund's thesis
    still fails the lens). Returns {"axis_scores": {"market": AxisScore}}.
    """
    score = AxisScore(
        axis="market",
        score=55.0,
        trend="improving",
        rationale="stub market rationale",
        confidence=0.6,
    )
    return {
        "axis_scores": {"market": score},
        "stage_timestamps": _stamp("axis_market"),
    }


def idea_vs_market_axis(state: GraphState) -> dict:  # noqa: ARG001  (stub: state used once real)
    """
    Score the FIT: does the idea survive scrutiny as-is — and if not, is
    this team strong enough to pivot? Reads the other evidence but NOT the
    other axes' outputs (independence is the point).
    Returns {"axis_scores": {"idea_vs_market": AxisScore}}.
    """
    score = AxisScore(
        axis="idea_vs_market",
        score=50.0,
        trend="stable",
        rationale="stub fit rationale",
        confidence=0.5,
    )
    return {
        "axis_scores": {"idea_vs_market": score},
        "stage_timestamps": _stamp("axis_idea_vs_market"),
    }


# -------------------------------- Diligence --------------------------------


def validator(state: GraphState) -> dict:
    """
    The self-correction agent (stretch goal 2 + core Trust requirement).
    For each Claim: verify_claim_external() -> assign TrustScore
    (verified / unverified / contradicted + confidence + evidence_ids);
    detect claim-vs-claim contradictions too. Writes trust onto claim rows
    (update_claim_trust). Increments validation_round.
    Returns: {"claims": updated, "contradictions": [...],
              "validation_round": n+1}.
    """
    round_n = state.get("validation_round", 0)
    # Stub: no contradictions found, so route_validation -> "ok".
    return {
        "contradictions": [],
        "validation_round": round_n + 1,
        "stage_timestamps": _stamp(f"validated_round_{round_n + 1}"),
    }


# --------------------------------- Outputs ---------------------------------


def memo_writer(state: GraphState) -> dict:
    """
    Strong-LLM generation of the 5 REQUIRED memo sections (snapshot,
    hypotheses, SWOT, problem&product, traction&KPIs). Hard rules enforced
    in the prompt AND post-validated in code:
      - every factual sentence cites claim/evidence ids,
      - missing data -> explicit entry in gaps ("Cap table: not
        disclosed"), NEVER fabricated,
      - no padding (brief: length counts against you).
    Attaches trace_ref (LangSmith run id). Writes: save_memo().
    Returns: {"memo": Memo(...)}.
    """
    memo = Memo(
        opportunity_id=state["opportunity_id"],
        sections={
            "snapshot": "stub",
            "hypotheses": "stub",
            "swot": "stub",
            "problem_product": "stub",
            "traction": "stub",
        },
        gaps=["Cap table: not disclosed"],
        recommendation="review",
    )
    tools.save_memo(memo)
    return {"memo": memo, "stage_timestamps": _stamp("memo_written")}


def decision_gate(state: GraphState) -> dict:
    """
    The human-in-the-loop pause. Graph is compiled with
    interrupt_before=["decision_gate"], so execution HALTS before this
    node with full state checkpointed; the API's POST /decision resumes it
    with Command(resume=DecisionRequest). This node body then simply
    validates/normalizes the injected human verdict.
    Returns: {"decision": Decision(...)}.
    """
    # The human's Decision is injected into state via Command(resume=...) /
    # update_state before this node runs (see agents.resume_run).
    return {"decision": state.get("decision"), "stage_timestamps": _stamp("decided")}


def memory_writeback(state: GraphState) -> dict:
    """
    The ONLY node that persists conclusions: finalize_opportunity() writes
    the decision, the three axis scores, the updated Founder Score point,
    and final timestamps in one transaction. Invariant: Memory holds only
    human-gated conclusions; provisional state lives in checkpoints.
    Returns: {"stage_timestamps": {..., "decided": now}}.
    """
    decision = state.get("decision")
    if decision is not None:
        tools.finalize_opportunity(
            state["opportunity_id"], decision, state.get("axis_scores", {})
        )
    return {"stage_timestamps": _stamp("written_back")}


# --------------- Routers (conditional edges — pure, no side effects) ---------------


def route_prescreen(state: GraphState) -> str:
    """
    After pre_screen: return "pass" -> fan out to the three axis nodes,
    or "reject" -> END (rejection already logged by the node).
    """
    prescreen = state.get("prescreen")
    return prescreen.verdict if prescreen else "pass"


def route_validation(state: GraphState) -> str:
    """
    After validator: if severe contradictions exist AND
    validation_round < 2, return "retry" -> re-run the axis agents with
    contradictions now visible in state; else return "ok" -> memo_writer.
    The hard cap prevents infinite loops (demo safety).
    """
    contradictions = state.get("contradictions", [])
    severe = any(c.severity == "high" for c in contradictions)
    if severe and state.get("validation_round", 0) < 2:
        return "retry"
    return "ok"
