"""Taxonomy + pydantic LLM contracts for claim generation (Q2/Q6 locked design)."""

from pydantic import BaseModel, Field

# The fixed claim taxonomy (Q2). Drives category-scoped matching + Founder Score rollup + memo.
CATEGORIES = (
    "education",
    "employment",
    "technical_skill",
    "open_source",
    "research",
    "achievement",
    "traction",
    "funding",
    "media",
    "affiliation",
)

# Category -> Founder Score component bucket (Q6). momentum is a recency cross-cut, not a bucket.
COMPONENT = {
    "technical_skill": "tech",
    "open_source": "tech",
    "research": "tech",
    "achievement": "execution",
    "traction": "execution",
    "funding": "execution",
    "education": "pedigree",
    "employment": "pedigree",
    "affiliation": "pedigree",
    "media": "influence",
}

# Default per-category weight into the Founder Score (fund weight_profile overrides later).
CATEGORY_WEIGHT = {
    "research": 1.0,
    "traction": 1.0,
    "open_source": 0.9,
    "funding": 0.9,
    "achievement": 0.85,
    "technical_skill": 0.7,
    "employment": 0.6,
    "affiliation": 0.6,
    "education": 0.5,
    "media": 0.4,
}


class ExtractedClaim(BaseModel):
    """One assertion the extractor derives from a founder's signals."""

    statement: str = Field(
        description="One canonical assertion about the founder, e.g. 'First-author paper at NeurIPS 2024'."
    )
    category: str = Field(description=f"Exactly one of: {', '.join(CATEGORIES)}")
    impact: float = Field(
        ge=0.0,
        le=1.0,
        description="Significance 0..1 (NeurIPS first-author ~0.9, 10k-star repo ~0.85, meetup talk ~0.2).",
    )
    attributes: dict = Field(
        default_factory=dict,
        description="Structured bits: {company,title,start,end} / {venue,year} / {metric,value}.",
    )
    dedup_key: str | None = Field(
        default=None,
        description="Stable deterministic key if obvious (arxiv id, github owner/repo, canonical url); else null.",
    )
    supporting_signals: list[int] = Field(
        default_factory=list,
        description="Indices of signals that SUPPORT this claim (>=1 required).",
    )
    refuting_signals: list[int] = Field(
        default_factory=list,
        description="Indices of signals that CONTRADICT this claim (usually empty).",
    )


class ClaimExtraction(BaseModel):
    claims: list[ExtractedClaim] = Field(default_factory=list)


class MatchDecision(BaseModel):
    """Warm-update adjudication: is a candidate the same fact as an existing claim?"""

    action: str = Field(
        description="'attach' if the SAME underlying fact as an existing claim, else 'mint'."
    )
    existing_index: int | None = Field(
        default=None, description="Index of the matched existing claim (attach only)."
    )
    stance: str = Field(
        default="supports", description="'supports' or 'refutes' the matched claim (attach only)."
    )
