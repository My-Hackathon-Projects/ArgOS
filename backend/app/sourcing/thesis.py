"""Default demo thesis (Q6 — hardcoded for now, swappable once the settings UI exists)."""

from app.sourcing.schemas import Thesis

DEFAULT_THESIS = Thesis(
    industries=["AI infrastructure", "robotics"],
    geo=["Germany", "Munich"],
    stage=["pre-seed", "seed"],
    keywords=["LLM infra", "autonomy", "robotics", "simulation", "edge ML"],
    founder_preferences={
        "schools": ["TUM", "LMU Munich", "ETH Zurich", "MIT"],
        "traits": ["technical", "ships open source", "no prior VC backing"],
    },
)
