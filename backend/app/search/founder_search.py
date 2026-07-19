"""NL compound / multi-attribute founder query (MVP requirement #3, FAQ #12).

Resolves a compound query like "technical founder, Berlin, AI infra, no prior VC backing,
top-tier accelerator" in ONE pass — not five filters. An LLM reasons over every founder's
attributes + claims at once, decomposes the query into sub-criteria, and returns the matching
founders ranked with a reason + which criteria each satisfies. Deterministic anchor: any
returned founder_id not in the real set is dropped (no hallucinated people).
"""

from typing import cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, Founder
from app.screening.llm import structured_llm


class SearchRequest(BaseModel):
    query: str


class FounderMatch(BaseModel):
    founder_id: str
    display_name: str | None
    founder_score: float | None
    current_company: str | None
    city: str | None
    relevance: float = Field(ge=0.0, le=1.0)
    reason: str
    matched: list[str]  # which query sub-criteria this founder satisfies


class FounderSearchResponse(BaseModel):
    query: str
    criteria: list[str]  # the compound query decomposed into sub-criteria
    matches: list[FounderMatch]


class _LLMMatch(BaseModel):
    founder_id: str
    relevance: float = Field(ge=0.0, le=1.0)
    reason: str
    matched: list[str] = Field(default_factory=list)


class _LLMOut(BaseModel):
    criteria: list[str] = Field(
        description="the compound query decomposed into its individual sub-criteria"
    )
    matches: list[_LLMMatch] = Field(default_factory=list)


def run_founder_search(db: Session, query: str) -> FounderSearchResponse:
    founders = db.execute(select(Founder)).scalars().all()
    by_id = {str(f.id): f for f in founders}

    lines = []
    for f in founders:
        claims = (
            db.execute(
                select(Claim.statement).where(Claim.founder_id == f.id).limit(15)
            )
            .scalars()
            .all()
        )
        lines.append(
            f"[{f.id}] {f.display_name} | {f.occupation or 'role?'} @ "
            f"{f.current_company or 'no company'} | city={f.city or '?'} | "
            f"FounderScore={f.founder_score} | claims: {'; '.join(claims) or 'none'}"
        )
    block = "\n".join(lines)

    prompt = f"""You resolve a COMPOUND VC founder search in ONE pass — reason over ALL attributes at once,
not as separate keyword filters. Move beyond keyword match: interpret each criterion semantically.

## Query
{query}

## Founders (id, role, company, city, Founder Score, claims)
{block}

## Task
1. Decompose the query into its individual sub-criteria (e.g. "technical", "Berlin", "AI infra",
   "no prior VC backing", "top-tier accelerator").
2. Return the founders that genuinely match, ranked by relevance (0..1). Interpret semantically:
   - "technical" / "AI infra" -> engineering / RAG / agent-orchestration / infra claims;
   - a geo criterion -> the founder's city;
   - "no prior VC backing" -> NO funding/investment/raised claims;
   - "top-tier accelerator" -> YC / Techstars / a16z / etc.
   Satisfy HARD constraints (geo, role) strictly; weigh soft ones.
3. Per match: founder_id EXACTLY as shown in [brackets], relevance, a one-line reason, and the list
   of sub-criteria it satisfies.

Rules: cite ONLY ids shown above; never invent a founder or a fact. Return only real matches
(fewer, correct beats many, loose)."""

    out = cast(_LLMOut, structured_llm(_LLMOut, smart=True).invoke(prompt))

    matches: list[FounderMatch] = []
    for m in out.matches:
        f = by_id.get(m.founder_id)  # anti-fabrication anchor
        if f is None:
            continue
        matches.append(
            FounderMatch(
                founder_id=m.founder_id,
                display_name=f.display_name,
                founder_score=f.founder_score,
                current_company=f.current_company,
                city=f.city,
                relevance=m.relevance,
                reason=m.reason,
                matched=m.matched,
            )
        )
    matches.sort(key=lambda x: -x.relevance)
    return FounderSearchResponse(query=query, criteria=out.criteria, matches=matches)
