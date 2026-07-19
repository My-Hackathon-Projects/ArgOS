"""Default demo thesis (Q6 — hardcoded for now, swappable once the settings UI exists)."""

from app.sourcing.schemas import Thesis

DEFAULT_THESIS = Thesis(
    industries=["AI infrastructure", "robotics", "machine learning"],
    geo=["Germany", "Munich", "Tübingen"],
    stage=["pre-idea", "pre-seed", "seed"],
    keywords=["LLM infra", "autonomy", "robotics", "simulation", "edge ML", "agents"],
    founder_preferences={
        "schools": ["TUM", "LMU Munich", "University of Tübingen", "ETH Zurich"],
        "communities": ["TUM.ai", "Cyber Valley", "ETH AI Center", "EuroTech"],
        "signals": [
            "hackathon winner/participant",
            "student club member",
            "stealth-mode / building in public",
            "ships open source",
            "research spinoff",
        ],
        "traits": ["technical", "no prior VC backing"],
    },
)
