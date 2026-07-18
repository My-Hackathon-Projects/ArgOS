"""Tools for the graph.

Define tools with the `@tool` decorator. The docstring becomes the tool
description the model sees, so keep it accurate and specific.
"""

from __future__ import annotations

from langchain_core.tools import tool


@tool
def search(query: str) -> str:
    """Search for information about a query.

    Args:
        query: The search query.

    Returns:
        A short text result.
    """
    # TODO: wire up a real search (Tavily, internal API, DB lookup, ...).
    return f"Placeholder result for: {query}"


# Register every tool here. Imported by nodes.py and agent.py.
tools = [search]
