"""Node functions for the graph.

Nodes take the current state and return a partial update dict (never mutate and
return the whole state). The model is bound to the tools once at import time.
"""

from __future__ import annotations

from typing import Literal

from langchain.chat_models import init_chat_model
from langgraph.graph import END

from my_agent.utils.state import AgentState
from my_agent.utils.tools import tools

SYSTEM_PROMPT = "You are a helpful assistant."

# Bind tools so the model can emit tool calls. Swap the model id as needed.
model = init_chat_model("anthropic:claude-sonnet-5").bind_tools(tools)


def call_model(state: AgentState) -> dict:
    """Invoke the LLM on the running message history.

    Returns a partial update appending the model's reply to `messages`.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}, *state["messages"]]
    response = model.invoke(messages)
    return {"messages": [response]}


def should_continue(state: AgentState) -> Literal["tools", END]:
    """Route to the tool node when the last message requested tool calls.

    Otherwise end the run.
    """
    last_message = state["messages"][-1]
    if getattr(last_message, "tool_calls", None):
        return "tools"
    return END
