"""Inbound pipeline agent — Graph 1 assembly + API-facing run helper.

Wiring (README §3):

    START → ingest_deck → resolve_entities → extract_claims → pre_screen
    pre_screen —route_prescreen→ {"pass": emit_ticket, "reject": END}
    emit_ticket → END

Trigger: ``POST /apply`` (multipart: company_name + deck PDF). The endpoint
returns ``{opportunity_id, status: "running"}`` in <1s and runs
``start_inbound_run`` as a background task. Thread-id convention (§2):
``thread_id = f"in:{opportunity_id}"``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from langgraph.graph import END, START, StateGraph

from app.service.checkpointer import get_checkpointer
from app.service.inboud_pipeline.utils import nodes
from app.service.inboud_pipeline.utils.models import InboundState
from app.service.models import Thesis


def build_inbound_graph():
    """Compile Graph 1. No interrupts — the single human gate lives in the
    validation pipeline (hard rule #10: exactly one human in the loop)."""
    builder = (
        StateGraph(InboundState)
        .add_node("ingest_deck", nodes.ingest_deck)
        .add_node("resolve_entities", nodes.resolve_entities)
        .add_node("extract_claims", nodes.extract_claims)
        .add_node("pre_screen", nodes.pre_screen)
        .add_node("emit_ticket", nodes.emit_ticket)
        .add_edge(START, "ingest_deck")
        .add_edge("ingest_deck", "resolve_entities")
        .add_edge("resolve_entities", "extract_claims")
        .add_edge("extract_claims", "pre_screen")
        .add_conditional_edges(
            "pre_screen",
            nodes.route_prescreen,
            {"pass": "emit_ticket", "reject": END},
        )
        .add_edge("emit_ticket", END)
    )
    return builder.compile(checkpointer=get_checkpointer())


# Module-level singleton (compiled once; also the langgraph.json entrypoint).
graph = build_inbound_graph()


def start_inbound_run(
    opportunity_id: str,
    company_name: str,
    deck_bytes: bytes,
    thesis: Thesis,
) -> InboundState:
    """
    Called by POST /apply as a background task. Builds state0 and runs the
    graph to completion (a passing application hands off to the validation
    pipeline inside ``emit_ticket``). Progress is observable via checkpoints
    on thread ``in:{opportunity_id}``.
    """
    state0: InboundState = {
        "opportunity_id": opportunity_id,
        "company_name": company_name,
        "raw_deck": deck_bytes,
        "thesis": thesis,
        "stage_timestamps": {"received": datetime.now(UTC).isoformat()},
    }
    return graph.invoke(
        state0, config={"configurable": {"thread_id": f"in:{opportunity_id}"}}
    )
