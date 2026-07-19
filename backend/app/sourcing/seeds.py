"""Hand-collected seed channels — the discovery starting points.

Client-facing: this is the "here's what we monitor for you" list. Later this moves
into the `sourcing_channel` table (UI-editable). `domain` scopes the Tavily search
(via include_domains); `domain=None` means open web (the channel name shapes the query).
"""

SEED_CHANNELS = [
    # Platform channels (domain-scoped)
    {"name": "Product Hunt", "type": "launch", "domain": "producthunt.com", "enabled": True},
    {
        "name": "Hacker News (Show HN)",
        "type": "launch",
        "domain": "news.ycombinator.com",
        "enabled": True,
    },
    {"name": "GitHub", "type": "code", "domain": "github.com", "enabled": True},
    {
        "name": "arXiv (research-paper authors)",
        "type": "paper",
        "domain": "arxiv.org",
        "enabled": True,
    },
    {"name": "Devpost (hackathons)", "type": "hackathon", "domain": "devpost.com", "enabled": True},
    # German / European AI founder ecosystem (open-web; the name drives the query)
    {"name": "TUM.ai student club members", "type": "club", "domain": None, "enabled": True},
    {
        "name": "Cyber Valley / TUM Venture Labs incubators",
        "type": "incubator",
        "domain": None,
        "enabled": True,
    },
    {
        "name": "AI hackathon winners & YC Startup School participants (LinkedIn)",
        "type": "community",
        "domain": None,
        "enabled": True,
    },
    {
        "name": "Stealth / building-in-public founders (LinkedIn, personal sites)",
        "type": "web",
        "domain": None,
        "enabled": True,
    },
    # Accelerator (kept off by default; enable to widen)
    {"name": "Y Combinator", "type": "accelerator", "domain": "ycombinator.com", "enabled": False},
]


def enabled_channels() -> list[dict]:
    return [c for c in SEED_CHANNELS if c["enabled"]]
