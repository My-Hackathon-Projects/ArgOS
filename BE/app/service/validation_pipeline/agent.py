"""Validation (processing) pipeline agent — Graph 3 assembly + run helpers.

Wiring (README §6):

    START → hydrate → [founder_axis, market_axis, idea_vs_market_axis]  # parallel fan-out
    [3 axes] → validator                                                # fan-in join
    validator —route_validation→ {"retry": [3 axes],  # severe contradictions, round < 2
                                  "ok": memo_writer}
    memo_writer → decision_gate → memory_writeback → END

Compiled with ``interrupt_before=["decision_gate"]`` — the single human in
the loop. Trigger: ``enqueue_processing(ticket)`` from an intake graph.
Thread-id convention (§2): ``thread_id = opportunity_id`` — the key joining
API routes, checkpoints, domain rows, and LangSmith traces.
"""

from __future__ import annotations

from datetime import datetime

from langgraph.graph import END, START, StateGraph

from app.service.checkpointer import get_checkpointer
from app.service.models import Decision, ProcessingTicket
from app.service.validation_pipeline.utils import nodes
from app.service.validation_pipeline.utils.models import ProcessingState

# The three parallel axis nodes — fanned out from hydrate AND on a validator retry.
_AXES = ["founder_axis", "market_axis", "idea_vs_market_axis"]


def _route_validation(state: ProcessingState):
    """retry -> re-fan-out to all three axes (contradictions now visible in
    state); ok -> memo_writer."""
    return _AXES if nodes.route_validation(state) == "retry" else "memo_writer"


def build_validation_graph():
    """Compile Graph 3 with the shared checkpointer and the one interrupt."""
    builder = (
        StateGraph(ProcessingState)
        .add_node("hydrate", nodes.hydrate)
        .add_node("founder_axis", nodes.founder_axis)
        .add_node("market_axis", nodes.market_axis)
        .add_node("idea_vs_market_axis", nodes.idea_vs_market_axis)
        .add_node("validator", nodes.validator)
        .add_node("memo_writer", nodes.memo_writer)
        .add_node("decision_gate", nodes.decision_gate)
        .add_node("memory_writeback", nodes.memory_writeback)
        .add_edge(START, "hydrate")
    )

    # Parallel fan-out: three static edges from hydrate run the axes concurrently.
    for axis in _AXES:
        builder.add_edge("hydrate", axis)
        # Fan-in join: validator waits for ALL three axes to finish.
        builder.add_edge(axis, "validator")

    # Retry loop (<= 2 rounds) or proceed to the memo.
    builder.add_conditional_edges(
        "validator", _route_validation, [*_AXES, "memo_writer"]
    )

    builder.add_edge("memo_writer", "decision_gate")
    builder.add_edge("decision_gate", "memory_writeback")
    builder.add_edge("memory_writeback", END)

    return builder.compile(
        checkpointer=get_checkpointer(),
        interrupt_before=["decision_gate"],
    )


# Module-level singleton (compiled once; also the langgraph.json entrypoint).
graph = build_validation_graph()


# --------------------------------------------------------------------------- #
# Run helpers — what the API layer and enqueue_processing() call.
# --------------------------------------------------------------------------- #
def _config(opportunity_id: str) -> dict:
    return {"configurable": {"thread_id": opportunity_id}}


def ticket_to_state(ticket: ProcessingTicket) -> ProcessingState:
    """
    Map the §5 handoff contract to the initial ProcessingState. Signals and
    claims are carried by id; ``hydrate`` re-loads them from Memory (the
    intake graph may also have placed hydrated copies in the invoke payload
    while the repository is stubbed).
    """
    return {
        "opportunity_id": ticket.opportunity_id,
        "track": ticket.track,
        "thesis": ticket.thesis,
        "validation_round": 0,
        "stage_timestamps": {"queued": ticket.handoff_at},
    }


def resume_run(opportunity_id: str, decision: Decision) -> ProcessingState:
    """
    Called by POST /decision/{opportunity_id} when the investor clicks
    Approve/Pass. Injects the human Decision into the checkpoint, then wakes
    the run paused before decision_gate; the graph executes decision_gate +
    memory_writeback and finishes. Returns the final state.

    (interrupt_before is a static interrupt, so we resume with invoke(None)
    after seeding the decision via update_state.)
    """
    config = _config(opportunity_id)
    graph.update_state(config, {"decision": decision})
    return graph.invoke(None, config)


def get_run_status(opportunity_id: str) -> dict:
    """
    Called by GET /opportunities/{id}/status. Reads the LATEST checkpoint
    for the thread and maps it to {stage, stage_timestamps, elapsed_seconds,
    awaiting_human} — zero extra bookkeeping, progress is already a
    checkpoint row.
    """
    snapshot = graph.get_state(_config(opportunity_id))
    values = snapshot.values or {}
    stamps: dict[str, str] = values.get("stage_timestamps", {})
    elapsed = None
    if stamps:
        times = sorted(datetime.fromisoformat(t) for t in stamps.values())
        elapsed = (times[-1] - times[0]).total_seconds()
    return {
        "stage": (snapshot.next[0] if snapshot.next else "done"),
        "stage_timestamps": stamps,
        "elapsed_seconds": elapsed,
        "awaiting_human": "decision_gate" in (snapshot.next or ()),
    }


def start_processing_run(ticket: ProcessingTicket) -> ProcessingState:
    """
    Direct entrypoint mirroring ``enqueue_processing``: run the graph up to
    the decision_gate interrupt on ``thread_id = opportunity_id``. Kept here
    so demos/tests can bypass the inbound graph.
    """
    return graph.invoke(ticket_to_state(ticket), _config(ticket.opportunity_id))
