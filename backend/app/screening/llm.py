"""Shared structured-output LLM helper for the screening/memo steps.

Mirrors app.claims.extract._llm — function_calling structured output over a Pydantic schema —
but typed (SecretStr) so it stays inside the type gate, and fail-fast if the key is missing.
"""

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.config import settings


def structured_llm(schema, *, smart: bool = True):
    key = settings.openai_api_key
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set — LLM screening/memo steps need it")
    model = settings.model_smart if smart else settings.model_fast
    return ChatOpenAI(model=model, api_key=SecretStr(key)).with_structured_output(
        schema, method="function_calling"
    )
