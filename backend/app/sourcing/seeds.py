"""Hand-collected seed channels — the discovery starting points.

Client-facing: this is the "here's what we monitor for you" list. Later this moves
into the `sourcing_channel` table (UI-editable). `domain` scopes the Tavily search
(via include_domains); `domain=None` means open web.
"""

SEED_CHANNELS = [
    {"name": "Product Hunt", "type": "launch", "domain": "producthunt.com", "enabled": True},
    {
        "name": "Hacker News (Show HN)",
        "type": "launch",
        "domain": "news.ycombinator.com",
        "enabled": True,
    },
    {"name": "Devpost (hackathons)", "type": "hackathon", "domain": "devpost.com", "enabled": True},
    {"name": "GitHub", "type": "code", "domain": "github.com", "enabled": True},
    {"name": "arXiv", "type": "paper", "domain": "arxiv.org", "enabled": True},
    {"name": "Y Combinator", "type": "accelerator", "domain": "ycombinator.com", "enabled": True},
    {"name": "MLH hackathons", "type": "hackathon", "domain": "mlh.io", "enabled": False},
    {"name": "Open web / personal sites", "type": "web", "domain": None, "enabled": True},
]


def enabled_channels() -> list[dict]:
    return [c for c in SEED_CHANNELS if c["enabled"]]
