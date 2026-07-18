"""State definition for the graph.

State is shared memory across all nodes. Store raw data here; format prompts
on-demand inside nodes. `messages` uses the built-in `add_messages` reducer so
each node appends rather than overwrites.
"""

from __future__ import annotations

from typing import Annotated

from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class AgentState(TypedDict):
    """Shared graph state.

    Attributes:
        messages: Conversation history. `add_messages` appends new messages and
            handles message-id de-duplication / updates.
    """

    messages: Annotated[list, add_messages]
