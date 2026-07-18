"""agents.py — graph assembly + API-facing run helpers.

Owns: (1) the main pipeline graph, (2) the outbound scanner sub-graph fired by
the scheduler, (3) ``start_run`` / ``resume_run`` / ``get_run_status`` — the
**only** functions FastAPI calls. ``thread_id == opportunity_id`` is the
correlation key across API, checkpoints, and LangSmith traces.

Dependency rule: agents.py imports nodes.py, which imports tools.py, which
imports models.py — never the other way.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

from langgraph.graph import END, START, StateGraph

from app.service import nodes
from app.service.models import Decision, GraphState, Thesis

# Names of the three parallel axis nodes — fanned out and joined in two places.
_AXES = ["founder_axis", "market_axis", "idea_vs_market_axis"]


# --------------------------------------------------------------------------- #
# Checkpointer
# --------------------------------------------------------------------------- #
def _postgres_dsn() -> str:
    """Reuse the FastAPI app's Postgres DSN, stripped to a plain psycopg DSN."""
    from app.core.config import settings

    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql"
    )


def get_checkpointer():
    """
    Return the PostgresSaver bound to the same database as the Memory
    layer (dev fallback: InMemorySaver). Checkpoints after every node give
    us crash-resume, the live status endpoint, time-to-decision metrics,
    and the replayable reasoning trace — all for free.

    Set ``SERVICE_CHECKPOINTER=postgres`` to use the shared Postgres DB;
    anything else (default) uses an in-memory saver so the pipeline runs in
    tests / local dev without a database.
    """
    if os.getenv("SERVICE_CHECKPOINTER", "memory").lower() == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        # Opened for the process lifetime (module-level singleton graph).
        # .setup() creates the checkpoints* tables (separate from Alembic).
        saver = PostgresSaver.from_conn_string(_postgres_dsn()).__enter__()
        saver.setup()
        return saver

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()


# --------------------------------------------------------------------------- #
# Main pipeline graph
# --------------------------------------------------------------------------- #
def _route_prescreen(state: GraphState):
    """pass -> fan out to the three axes; reject -> END."""
    return _AXES if nodes.route_prescreen(state) == "pass" else END


def _route_validation(state: GraphState):
    """retry -> re-run the three axes (contradictions now in state); ok -> memo."""
    return _AXES if nodes.route_validation(state) == "retry" else "memo_writer"


def build_main_graph():
    """
    Wire the StateGraph(GraphState):

      START -> ingest -> resolve_entities -> extract_claims -> pre_screen
      pre_screen --route_prescreen--> {"pass": [founder_axis, market_axis,
                                       idea_vs_market_axis],   # parallel
                                       "reject": END}
      [3 axes] -> validator                                     # join
      validator --route_validation--> {"retry": [3 axes],       # loop <=2
                                       "ok": memo_writer}
      memo_writer -> decision_gate -> memory_writeback -> END

    Compile with checkpointer=get_checkpointer() and
    interrupt_before=["decision_gate"] (the one human in the loop).
    Return the compiled app. Module-level singleton is fine.
    """
    builder = StateGraph(GraphState)

    builder.add_node("ingest", nodes.ingest)
    builder.add_node("resolve_entities", nodes.resolve_entities)
    builder.add_node("extract_claims", nodes.extract_claims)
    builder.add_node("pre_screen", nodes.pre_screen)
    builder.add_node("founder_axis", nodes.founder_axis)
    builder.add_node("market_axis", nodes.market_axis)
    builder.add_node("idea_vs_market_axis", nodes.idea_vs_market_axis)
    builder.add_node("validator", nodes.validator)
    builder.add_node("memo_writer", nodes.memo_writer)
    builder.add_node("decision_gate", nodes.decision_gate)
    builder.add_node("memory_writeback", nodes.memory_writeback)

    builder.add_edge(START, "ingest")
    builder.add_edge("ingest", "resolve_entities")
    builder.add_edge("resolve_entities", "extract_claims")
    builder.add_edge("extract_claims", "pre_screen")

    # pre_screen -> fan out to the 3 axes (parallel) or END
    builder.add_conditional_edges("pre_screen", _route_prescreen, [*_AXES, END])

    # each axis joins at the validator (validator waits for all three)
    for axis in _AXES:
        builder.add_edge(axis, "validator")

    # validator -> retry the axes (<=2) or proceed to the memo
    builder.add_conditional_edges("validator", _route_validation, [*_AXES, "memo_writer"])

    builder.add_edge("memo_writer", "decision_gate")
    builder.add_edge("decision_gate", "memory_writeback")
    builder.add_edge("memory_writeback", END)

    return builder.compile(
        checkpointer=get_checkpointer(),
        interrupt_before=["decision_gate"],
    )


# --------------------------------------------------------------------------- #
# Outbound scanner sub-graph
# --------------------------------------------------------------------------- #
def build_scanner_graph():
    """
    The outbound sourcing sub-graph, triggered by the scheduler (cron):

      START -> scan_channels (github/hn/arxiv via tools) -> resolve ->
      quick_score (same axes lens, thin) -> threshold gate:
        above  -> draft_outreach -> persist to outbound queue
        below  -> persist signals only (Memory keeps everything)

    When an activated founder actually applies, that becomes a normal
    inbound run through build_main_graph() — one funnel, per brief.
    Kept separate so a slow scan can never block a live application.
    """
    from app.service import tools

    def scan_channels(state: GraphState) -> dict:
        thesis: Thesis = state.get("thesis") or Thesis()
        q = " ".join(thesis.sectors) or "ai"
        signals = (
            tools.scan_github(q, 20)
            + tools.scan_hackernews(q, 20)
            + tools.scan_arxiv(q, 20)
        )
        tools.save_signals(signals)
        return {"signals": signals}

    def resolve(state: GraphState) -> dict:
        return nodes.resolve_entities(state)

    def quick_score(state: GraphState) -> dict:
        # Thin reuse of the founder lens for a cheap sourcing score.
        return nodes.founder_axis(state)

    def threshold_gate(state: GraphState) -> dict:
        founder = state.get("founder")
        signals = state.get("signals", [])
        thesis = state.get("thesis") or Thesis()
        score = state.get("axis_scores", {}).get("founder")
        if founder and score and score.score >= 60:
            _draft = tools.draft_outreach(founder, signals, thesis)
            # TODO: persist to outbound queue (draft shown in UI).
        return {}

    builder = StateGraph(GraphState)
    builder.add_node("scan_channels", scan_channels)
    builder.add_node("resolve", resolve)
    builder.add_node("quick_score", quick_score)
    builder.add_node("threshold_gate", threshold_gate)
    builder.add_edge(START, "scan_channels")
    builder.add_edge("scan_channels", "resolve")
    builder.add_edge("resolve", "quick_score")
    builder.add_edge("quick_score", "threshold_gate")
    builder.add_edge("threshold_gate", END)
    # Sub-graph: no interrupts, opt out of checkpointing.
    return builder.compile(checkpointer=False)


# Module-level singletons (compiled once).
main_graph = build_main_graph()
scanner_graph = build_scanner_graph()


# --------------------------------------------------------------------------- #
# API-facing run helpers — the ONLY functions FastAPI calls.
# --------------------------------------------------------------------------- #
def _config(opportunity_id: str) -> dict:
    return {"configurable": {"thread_id": opportunity_id}}


def start_run(
    opportunity_id: str, track: str, thesis: Thesis, intake_payload: dict
) -> None:
    """
    Called by POST /apply (background task — the endpoint returns
    {opportunity_id, status: "running"} in <1s). Builds state0
    (ids, track, thesis, stage_timestamps={"received": now}) and calls
    graph.invoke(state0, config={"configurable":
    {"thread_id": opportunity_id}}). Fire-and-forget: progress is
    observable via checkpoints, not via this call's return value.

    Runs the pipeline up to the decision_gate interrupt, where it halts
    with full state checkpointed until resume_run() is called.
    """
    state0: GraphState = {
        "opportunity_id": opportunity_id,
        "track": track,  # type: ignore[typeddict-item]
        "thesis": thesis,
        "signals": intake_payload.get("signals", []),
        "validation_round": 0,
        "stage_timestamps": {"received": datetime.now(UTC).isoformat()},
    }
    main_graph.invoke(state0, _config(opportunity_id))


def resume_run(opportunity_id: str, decision: Decision) -> GraphState:
    """
    Called by POST /decision/{opp_id} when the investor clicks
    Approve/Pass. Injects the human Decision, then wakes the run paused at
    decision_gate; the graph executes decision_gate + memory_writeback and
    finishes. Returns final state so the endpoint can render the final
    MemoView.

    (interrupt_before is a static interrupt, so we resume with invoke(None)
    after seeding the decision via update_state.)
    """
    config = _config(opportunity_id)
    main_graph.update_state(config, {"decision": decision})
    return main_graph.invoke(None, config)


def get_run_status(opportunity_id: str) -> dict:
    """
    Called by GET /opportunities/{id}/status (frontend polls ~2s).
    Reads the LATEST CHECKPOINT for thread_id (graph.get_state) and maps
    it to {stage, stage_timestamps, elapsed_seconds, awaiting_human}.
    Zero extra bookkeeping — orchestration progress is already a DB row.
    """
    snapshot = main_graph.get_state(_config(opportunity_id))
    values = snapshot.values or {}
    stamps: dict[str, str] = values.get("stage_timestamps", {})
    awaiting_human = "decision_gate" in (snapshot.next or ())
    elapsed = None
    if stamps:
        times = sorted(datetime.fromisoformat(t) for t in stamps.values())
        elapsed = (times[-1] - times[0]).total_seconds()
    return {
        "stage": (snapshot.next[0] if snapshot.next else "done"),
        "stage_timestamps": stamps,
        "elapsed_seconds": elapsed,
        "awaiting_human": awaiting_human,
    }


def trigger_scan(thesis: Thesis) -> None:
    """
    Called by the scheduler (APScheduler cron every N minutes) and by a
    manual "Scan now" button for the demo. Runs build_scanner_graph()
    over the thesis-relevant channels/queries.
    """
    scanner_graph.invoke({"thesis": thesis})
