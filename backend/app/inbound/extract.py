"""Inbound LLM steps — deck claim extraction + thesis pre-screen viability check.

Prompts ported from BE/app/service (inboud_pipeline extract_claims + pre_screen),
re-idiomatized onto app.screening.llm.structured_llm. Both use the fast model.
"""

from typing import Literal, cast

from pydantic import BaseModel, Field

from app.screening.llm import structured_llm


class DeckClaim(BaseModel):
    """One checkable factual assertion extracted from a deck page."""

    category: Literal["traction", "revenue", "team", "market", "product"]
    statement: str = Field(description="Verbatim-faithful assertion, e.g. '$50K MRR as of Q2 2026'.")
    source_page: int = Field(ge=1, description="1-based deck page the assertion appears on.")


class DeckExtraction(BaseModel):
    """Output of the one-pass deck extraction call."""

    idea: str | None = Field(default=None, description="One sentence: what the company does. null if the deck doesn't say.")
    sector: str | None = Field(default=None, description="Lowercase sector label, e.g. 'fintech', 'robotics'. null if unclear.")
    geo: str | None = Field(default=None, description="Primary geography, e.g. 'US', 'EU'. null if unclear.")
    claims: list[DeckClaim] = Field(default_factory=list)


class PreScreenResult(BaseModel):
    """Cheap kill-filter verdict. Rejections must carry a reason — they are logged, never silent."""

    verdict: Literal["pass", "reject"]
    reason: str


def _pages_block(pages: list[tuple[int, str]]) -> str:
    return "\n\n".join(f"[deck p.{n}]\n{text}" for n, text in pages if text) or "(no deck text)"


def extract_deck(company_name: str, pages: list[tuple[int, str]]) -> DeckExtraction:
    """One fast-LLM pass: company profile (idea/sector/geo) + checkable claims with page pointers."""
    prompt = f"""You are extracting structured facts from an inbound pitch deck for '{company_name}'.

## Deck pages
{_pages_block(pages)}

## Task
1. Profile: idea (one sentence, what the company does), sector (lowercase label), geo. Use null when
   the deck does not say — never guess.
2. Claims: every CHECKABLE factual assertion (traction, revenue, team, market, product). A claim must
   be specific enough to verify or refute later ('$50K MRR', 'ex-Google founding team', '10k users').
   Skip vision statements, adjectives, and unfalsifiable marketing copy.

## Rules
- statement stays verbatim-faithful to the deck; never embellish, never merge two assertions.
- source_page is the [deck p.N] page the assertion appears on. Only cite pages shown above.

Return the structured extraction now."""
    return cast(DeckExtraction, structured_llm(DeckExtraction, smart=False).invoke(prompt))


def prescreen_llm(thesis: dict, pages: list[tuple[int, str]]) -> PreScreenResult:
    """Fast-LLM viability check — the second pre-screen stage after the code hard filters."""
    prompt = f"""You are the cheap pre-screen filter of a VC funnel. Decide pass/reject for this inbound
application against the fund thesis.

## Fund thesis
{thesis or "(no thesis configured — judge basic viability only)"}

## Application (deck pages)
{_pages_block(pages)}

## Rules
- reject ONLY on clear, explainable misfit (obviously outside the thesis) or clear non-viability
  (no discernible product/idea at all).
- UNCERTAIN => pass. The deep 3-axis screening happens downstream; this filter only kills obvious noise.
- reason: one concrete sentence naming what the verdict rests on.

Return the structured verdict now."""
    return cast(PreScreenResult, structured_llm(PreScreenResult, smart=False).invoke(prompt))
