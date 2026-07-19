"""Pydantic contracts for the market-research graph (LLM structured outputs).

Every extractor cites its evidence by index into the hits it was given (`citation_indices`);
persist maps those indices back to signals -> urls for end-to-end provenance. Numbers are never
invented: each `Figure` carries a `basis` of reported | estimated_bottom_up | gap.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LLMOut(BaseModel):
    """Base for LLM structured outputs: coerce explicit null -> [] on list fields.

    Models frequently emit `"investors": null` for an empty list; pydantic's default_factory only
    fires when the key is ABSENT, not when it is null, so without this the whole extraction fails.
    """

    @model_validator(mode="before")
    @classmethod
    def _none_lists_to_empty(cls, data):
        if isinstance(data, dict):
            for name, f in cls.model_fields.items():
                if data.get(name) is None:
                    ann = f.annotation
                    if ann is list or getattr(ann, "__origin__", None) is list:
                        data[name] = []
        return data


# Sub-goals that queries + hits are tagged by (shared tagged search pool).
SUBGOALS = ("sizing", "competition", "comparables", "kpi", "trend")

# Market-claim categories (claim.category is free-text; these are the market agent's slice).
CLAIM_CATEGORIES = ("market_size", "competition", "comparable", "market")

BASIS = ("reported", "estimated_bottom_up", "gap")


class OpportunityInput(LLMOut):
    """The market-research subject. Runs only when there is an idea/sector to size."""

    founder_id: str | None = None
    company_name: str | None = None
    idea: str = Field(description="The product / idea / topic being evaluated.")
    sector: str | None = None
    geo: str | None = None

    def has_subject(self) -> bool:
        return bool((self.idea or "").strip() or (self.sector or "").strip())


class MarketQuery(LLMOut):
    query: str
    subgoal: Literal["sizing", "competition", "comparables", "kpi", "trend"]
    domain: str | None = None  # scope Tavily to this domain; None = open web
    rationale: str = ""


class MarketSearchPlan(LLMOut):
    queries: list[MarketQuery] = Field(default_factory=list)


class Figure(LLMOut):
    """One cited quantity — TAM/SAM/SOM/CAGR or a KPI band. Never a bare invented number."""

    metric: str = Field(
        description="e.g. TAM, SAM, SOM, CAGR, CAC, CPC, LTV, gross_margin, ACV, seed_round_size"
    )
    value: str | None = Field(
        default=None,
        description="Value with units/range as a string ('$4.2B', '18%'); null when basis=gap.",
    )
    unit: str | None = None
    basis: Literal["reported", "estimated_bottom_up", "gap"]
    assumptions: list[str] = Field(
        default_factory=list,
        description="For estimated_bottom_up: the derivation + cited inputs. Empty for reported.",
    )
    citation_indices: list[int] = Field(
        default_factory=list,
        description="Indices of source hits backing this figure. Required unless basis=gap.",
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    note: str = ""


class MarketSizing(LLMOut):
    figures: list[Figure] = Field(
        default_factory=list, description="TAM, SAM, SOM (+ CAGR). Gap-flag what is not found."
    )
    market_maturity: str | None = Field(
        default=None, description="emerging | growing | mature | declining | unknown"
    )
    summary: str = ""


class Competitor(LLMOut):
    name: str
    cluster: str | None = Field(
        default=None, description="incumbent | challenger | emerging | adjacent"
    )
    positioning: str = ""
    is_emerging_threat: bool = False
    citation_indices: list[int] = Field(default_factory=list)


class Competition(LLMOut):
    competitors: list[Competitor] = Field(default_factory=list)
    concentration: str | None = Field(
        default=None, description="fragmented | moderate | concentrated | unknown"
    )
    summary: str = ""


class Comparable(LLMOut):
    """A similar startup that RAISED — the funding benchmark (amount cited-or-gap)."""

    name: str
    one_liner: str = ""
    stage: str | None = None
    round_size: str | None = Field(
        default=None, description="null when undisclosed (still a valid comp)."
    )
    valuation: str | None = None
    investors: list[str] = Field(default_factory=list)
    date: str | None = None
    similarity_rationale: str = ""
    citation_indices: list[int] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class Comparables(LLMOut):
    comparables: list[Comparable] = Field(default_factory=list)
    summary: str = ""


class KpiBenchmarks(LLMOut):
    benchmarks: list[Figure] = Field(
        default_factory=list, description="CAC, CPC, LTV, gross_margin, ACV, seed_round_size."
    )
    summary: str = ""


# ── synthesis / axis ─────────────────────────────────────────────────────────
class Hypothesis(LLMOut):
    statement: str
    kind: Literal["bull", "bear"] = "bull"


class MarketAxis(LLMOut):
    verdict: Literal["bull", "neutral", "bear"]
    score: float = Field(ge=0.0, le=100.0, description="0..100, thesis-relative attractiveness.")
    trend: Literal["improving", "declining", "stable"] = Field(description="market-momentum proxy")
    rationale: str = Field(description="Grounded in the findings; names the evidence it rests on.")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class MarketSynthesis(LLMOut):
    hypotheses: list[Hypothesis] = Field(default_factory=list)
    opportunities: list[str] = Field(
        default_factory=list, description="SWOT — market Opportunities."
    )
    threats: list[str] = Field(default_factory=list, description="SWOT — market Threats.")
    why_now: str = ""
    axis: MarketAxis
    gaps: list[str] = Field(
        default_factory=list, description="Flagged missing/unverified data (scored as honesty)."
    )
