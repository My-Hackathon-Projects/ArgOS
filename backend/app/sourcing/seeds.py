"""Hand-collected seed channels — the discovery starting points.

Client-facing: this is the "here's what we monitor for you" list. Later this moves
into the `sourcing_channel` table (UI-editable). `domain` scopes the Tavily search
(via include_domains); `domain=None` means open web (the channel name + thesis shape
the query). Names are geo-GENERIC — geo/school/community specificity comes from the thesis
(founder_preferences.communities), never hardcoded here.

Coverage maps to the Challenge-2 brief (GitHub, launches, hackathons, papers/patents,
accelerator cohorts; Crunchbase/LinkedIn/ProductHunt/HN/arXiv/patents/Twitter) plus
Evertrace-style primary-event sources (patents, X co-founder-search, build-in-public).
"""

SEED_CHANNELS = [
    # ── Primary / high-signal builder sources ──
    {
        "name": "GitHub — repos, commits, releases",
        "type": "code",
        "domain": "github.com",
        "enabled": True,
    },
    {
        "name": "arXiv — research-paper authors",
        "type": "paper",
        "domain": "arxiv.org",
        "enabled": True,
    },
    {
        "name": "Google Patents — inventors",
        "type": "patent",
        "domain": "patents.google.com",
        "enabled": True,
    },
    # ── Launches ──
    {
        "name": "Product Hunt — launches",
        "type": "launch",
        "domain": "producthunt.com",
        "enabled": True,
    },
    {
        "name": "Hacker News — Show HN",
        "type": "launch",
        "domain": "news.ycombinator.com",
        "enabled": True,
    },
    # ── Hackathons ──
    {
        "name": "Devpost — hackathon projects",
        "type": "hackathon",
        "domain": "devpost.com",
        "enabled": True,
    },
    {
        "name": "Major League Hacking — hackathons",
        "type": "hackathon",
        "domain": "mlh.io",
        "enabled": True,
    },
    # ── Company / funding intelligence ──
    {
        "name": "Crunchbase — companies & funding",
        "type": "company",
        "domain": "crunchbase.com",
        "enabled": True,
    },
    # ── Public social footprint (Area of Research 3) ──
    {
        "name": "LinkedIn — public profiles & posts",
        "type": "social",
        "domain": "linkedin.com",
        "enabled": True,
    },
    {
        "name": "X / Twitter — build-in-public & co-founder search",
        "type": "social",
        "domain": None,
        "enabled": True,
    },
    # ── Accelerators, incubators & student clubs (thesis communities drive these) ──
    {
        "name": "Accelerator & incubator cohorts (YC, EF, Antler, Techstars + thesis communities)",
        "type": "accelerator",
        "domain": None,
        "enabled": True,
    },
    {
        "name": "AI student clubs & university labs (from thesis communities)",
        "type": "club",
        "domain": None,
        "enabled": True,
    },
    # ── Stealth / building-in-public ──
    {
        "name": "Stealth / building-in-public founders (personal sites)",
        "type": "web",
        "domain": None,
        "enabled": True,
    },
]


def enabled_channels() -> list[dict]:
    return [c for c in SEED_CHANNELS if c["enabled"]]
