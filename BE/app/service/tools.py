"""Shared service tools — centralized LLM factories.

Model choice/config is one line to change (or one env var: FAST_LLM_MODEL /
STRONG_LLM_MODEL). Always used with ``.with_structured_output(<Model>)`` —
free-text responses are banned pipeline-wide.
"""

from __future__ import annotations

import os

from langchain.chat_models import init_chat_model
from langchain_core.language_models.chat_models import BaseChatModel


def get_fast_llm() -> BaseChatModel:
    """
    Return the cheap/fast chat model, used by pre_screen and claim
    extraction.
    """
    model = os.environ.get("FAST_LLM_MODEL", "openai:gpt-4o-mini")
    return init_chat_model(model, temperature=0)


def get_strong_llm() -> BaseChatModel:
    """
    Return the strong reasoning model, used by the three axis agents, the
    validator, and the memo writer.
    """
    model = os.environ.get("STRONG_LLM_MODEL", "openai:gpt-4o")
    return init_chat_model(model, temperature=0)
