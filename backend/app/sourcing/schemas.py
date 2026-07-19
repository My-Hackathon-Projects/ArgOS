"""Pydantic contracts for the discovery graph (LLM structured outputs)."""

from pydantic import BaseModel, Field


class Thesis(BaseModel):
    industries: list[str]
    geo: list[str] = []
    stage: list[str] = []
    keywords: list[str] = []
    founder_preferences: dict = Field(default_factory=dict)


class SearchQuery(BaseModel):
    query: str
    channel: str
    domain: str | None = None  # scope Tavily to this domain; None = open web
    rationale: str = ""


class SearchPlan(BaseModel):
    queries: list[SearchQuery]


class Candidate(BaseModel):
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    city: str | None = None
    occupation: str | None = None
    current_company: str | None = None  # None = pre-company founder (primary target)
    github: str | None = None
    twitter: str | None = None
    linkedin: str | None = None
    website: str | None = None
    orcid: str | None = None
    why_relevant: str = ""
    source_urls: list[str] = []


class CandidateList(BaseModel):
    candidates: list[Candidate]


class Education(BaseModel):
    school: str | None = None
    degree: str | None = None
    field: str | None = None
    year: int | None = None


class ExtractedSignal(BaseModel):
    source: str | None = None  # github|arxiv|hn|producthunt|linkedin|web...
    signal_type: str  # commit|repo|paper|launch|hackathon|profile|post|news...
    canonical_url: str
    title: str = ""
    summary: str = ""
    occurred_at: str | None = None  # ISO date if known


class CandidateResearch(BaseModel):
    resolved_name: str | None = None  # the person's REAL full name if the candidate was a handle
    education: list[Education] = []
    extra_signals: list[ExtractedSignal] = []
    notes: str = ""
