"""Graph construction.

Wires nodes and edges into a compiled graph. `langgraph.json` points at the
`graph` variable exported here.

Flow:
    START -> agent -> (tool_calls?) -> tools -> agent -> ... -> END
"""

from __future__ import annotations

from langgraph.graph import START, StateGraph
from langgraph.prebuilt import ToolNode

from my_agent.utils.nodes import call_model, should_continue
from my_agent.utils.state import AgentState
from my_agent.utils.tools import tools

# ToolNode executes any tool calls emitted by the model and returns ToolMessages.
tool_node = ToolNode(tools, handle_tool_errors=True)

graph = (
    StateGraph(AgentState)
    .add_node("agent", call_model)
    .add_node("tools", tool_node)
    .add_edge(START, "agent")
    .add_conditional_edges("agent", should_continue, ["tools", "__end__"])
    .add_edge("tools", "agent")
    .compile()
)
