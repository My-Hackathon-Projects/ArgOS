"""Discovery graph (Q10 blueprint, scaled up).

Nodes:  plan_searches -> run_searches -> extract_candidates -> research_candidates -> finalize
- plan/screen use the fast model; per-founder synthesis uses the smart model (gpt-5.4).
- run_searches + research_candidates fan out in a thread pool (parallel Tavily + LLM I/O).
- research is recursive: N search rounds per founder, then one synthesis pass.
Seeds (app/sourcing/seeds.py) drive the channels; the thesis rides in every prompt.
finalize hands back an in-memory delivery; persistence is a separate single-writer step.
Auto-traced to LangSmith when LANGSMITH_TRACING=true.

Future: add OpenAI's native web-search tool as a SECOND source in run_searches (union + dedup).
"""

import hashlib
import operator
import re
import unicodedata
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from typing import Annotated, TypedDict
from urllib.parse import urlsplit, urlunsplit

import httpx
from langchain_openai import ChatOpenAI
from langgraph.graph import END, START, StateGraph

from app.config import settings
from app.sourcing import tavily
from app.sourcing.schemas import CandidateList, CandidateResearch, SearchPlan
from app.sourcing.seeds import enabled_channels

# Per-source priors (Q-D) — downstream Trust weights by these.
SOURCE_RELIABILITY = {
    "arxiv": 0.9,
    "github": 0.85,
    "crunchbase": 0.85,
    "accelerator": 0.8,
    "devpost": 0.7,
    "mlh": 0.7,
    "producthunt": 0.7,
    "news": 0.6,
    "personal_site": 0.6,
    "linkedin": 0.55,
    "youtube": 0.5,
    "hn": 0.5,
    "post": 0.5,
    "web": 0.4,
}

_TRACKING = {
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
    "fbclid",
    "gclid",
    "ref",
    "ref_src",
}


class DiscoveryState(TypedDict, total=False):
    thesis: dict
    queries: list[dict]
    hits: list[dict]
    candidates: list[dict]
    founders: list[dict]
    stats: dict
    trace: Annotated[list[str], operator.add]


def _llm(schema, smart: bool = False):
    model = settings.model_smart if smart else settings.model_fast
    return ChatOpenAI(model=model, api_key=settings.openai_api_key).with_structured_output(schema)


def _canonicalize(url: str) -> str:
    if not url:
        return url
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    q = sorted(kv for kv in parts.query.split("&") if kv and kv.split("=")[0] not in _TRACKING)
    path = parts.path.rstrip("/") or "/"
    return urlunsplit((parts.scheme.lower() or "https", host, path, "&".join(q), ""))


def _content_hash(title: str | None, summary: str | None) -> str | None:
    words = " ".join((title or "", summary or "")).lower().split()
    return hashlib.sha256(" ".join(words).encode()).hexdigest() if words else None


def _infer_source(url: str) -> str:
    u = (url or "").lower()
    for needle, src in (
        ("arxiv.org", "arxiv"),
        ("github.com", "github"),
        ("producthunt.com", "producthunt"),
        ("news.ycombinator.com", "hn"),
        ("linkedin.com", "linkedin"),
        ("crunchbase.com", "crunchbase"),
        ("youtube.com", "youtube"),
        ("youtu.be", "youtube"),
        ("devpost.com", "devpost"),
        ("mlh.io", "mlh"),
    ):
        if needle in u:
            return src
    return "web"


def _handle(value: str | None, host: str) -> str | None:
    if not value:
        return value
    m = re.search(host + r"/([A-Za-z0-9_.-]+)", value)
    return (m.group(1) if m else value).lstrip("@")


def _derive_identity(cand: dict, signals: list[dict]) -> dict:
    ident = {k: cand.get(k) for k in ("github", "twitter", "linkedin", "website", "orcid")}
    for s in signals:
        url = s["canonical_url"]
        low = url.lower()
        if not ident["github"] and "github.com/" in low:
            m = re.search(r"github\.com/([A-Za-z0-9_.-]+)", url)
            if m and m.group(1).lower() not in ("orgs", "topics", "search", "about"):
                ident["github"] = m.group(1)
        if not ident["linkedin"] and "linkedin.com/in/" in low:
            m = re.search(r"linkedin\.com/in/([A-Za-z0-9%-]+)", url)
            if m:
                ident["linkedin"] = f"https://www.linkedin.com/in/{m.group(1)}"
        if not ident["twitter"] and ("twitter.com/" in low or "x.com/" in low):
            m = re.search(r"(?:twitter|x)\.com/([A-Za-z0-9_]+)", url)
            if m and m.group(1).lower() not in ("i", "home", "search", "share"):
                ident["twitter"] = m.group(1)
    ident["github"] = _handle(ident["github"], "github.com")
    ident["twitter"] = _handle(ident["twitter"], r"(?:twitter|x)\.com")
    return ident


def _split_name(full: str | None) -> tuple[str | None, str | None]:
    parts = (full or "").split()
    if len(parts) >= 2:
        return parts[0], parts[-1]
    return None, None


def _norm(s: str | None) -> str:
    d = unicodedata.normalize("NFKD", (s or "").lower().strip())
    return " ".join("".join(c for c in d if not unicodedata.combining(c)).split())


def _worth_researching(cand: dict) -> bool:
    """Cheap gate before the expensive synthesis: skip junk (no name / 'None' / no identity)."""
    name = (cand.get("display_name") or "").strip()
    if not name or name.lower() == "none":
        return False
    has_full_name = len(name.split()) >= 2
    has_identity = any(cand.get(k) for k in ("github", "linkedin", "website", "orcid", "twitter"))
    return has_full_name or has_identity


# ── ① plan_searches (fast model, structured prompt) ──────────────────────────
def plan_searches(state: DiscoveryState) -> dict:
    t = state["thesis"]
    geo = ", ".join(t.get("geo") or []) or "any"
    prefs = t.get("founder_preferences") or {}
    schools = ", ".join(prefs.get("schools") or []) or "any relevant university"
    communities = ", ".join(prefs.get("communities") or []) or "relevant student clubs / incubators"
    signals = (
        ", ".join(prefs.get("signals") or [])
        or "active building (code, launches, papers, hackathons)"
    )
    channels = enabled_channels()
    chan_lines = "\n".join(
        f"- {c['name']} (type={c['type']}, domain={c['domain'] or 'null (open web)'})"
        for c in channels
    )
    prompt = f"""You are a VC sourcing strategist specializing in early-stage founder discovery.

## Investment Thesis
- Industries: {t["industries"]}
- Geography: {t["geo"]}
- Stage: {t["stage"]}
- Technical focus: {t["keywords"]}
- Founder profile: {t["founder_preferences"]}

## Seed Discovery Channels
{chan_lines}

## Task
Write up to {settings.queries_per_channel} search queries PER channel to discover EARLY-STAGE and
PRE-FOUNDERS — people who may NOT have a company yet: research-paper authors, hackathon
participants/winners, student-club members, strong student open-source builders, competition
winners. "No company yet" is a POSITIVE signal — find them BEFORE they found.

## How to write good queries
1. NATURAL LANGUAGE ONLY. Do NOT use search operators — no `site:`, no boolean OR/AND, no
   `-negation`, no long quoted OR-blocks. The search API is neural; plain descriptive phrases work
   best, and the domain is already scoped separately.
2. ONE concrete angle per query. Prefer NAMED entities over abstract institution names — infer and
   name real local hackathons, specific university labs/chairs and their professors, named student
   clubs, named accelerator cohorts, notable local repos/competitions (from the thesis geo +
   schools {schools} + communities {communities}). Split a list of schools into SEPARATE per-school
   queries rather than one combined block.
3. Bias to the thesis geography ({geo}) and to the founder signals ({signals}); target people, not
   companies.
4. For each query set `channel` to the channel name and `domain` to its domain (null = open web).

Generate the queries now."""
    plan = _llm(SearchPlan).invoke(prompt)
    queries = [q.model_dump() for q in plan.queries][: settings.max_search_queries]
    return {
        "queries": queries,
        "trace": [f"plan_searches -> {len(queries)} queries over {len(channels)} channels"],
    }


# ── ② run_searches (parallel Tavily) ─────────────────────────────────────────
def _search_one(q: dict) -> list[dict]:
    domains = [q["domain"]] if q.get("domain") else None
    try:
        res = tavily.tavily_search(
            q["query"],
            settings.tavily_api_key,
            max_results=settings.tavily_max_results,
            include_domains=domains,
            search_depth="advanced",
            include_raw_content=True,
        )
    except httpx.HTTPError:
        return []  # one flaky query must not sink the fan-out (narrow, not silent)
    return [
        {
            "channel": q.get("channel"),
            "title": r.get("title"),
            "url": r.get("url"),
            # raw_content (fuller page) surfaces author/member/participant names snippets miss
            "content": (r.get("raw_content") or r.get("content") or "")[
                : settings.hit_content_chars
            ],
        }
        for r in res.get("results", [])
    ]


def run_searches(state: DiscoveryState) -> dict:
    queries = state["queries"]
    hits: list[dict] = []
    seen: set[str] = set()
    with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
        for batch in ex.map(_search_one, queries):
            for h in batch:
                # Dedup on the CANONICAL url so www/scheme/param variants collapse (not raw url).
                key = _canonicalize(h["url"]) if h.get("url") else None
                if key and key not in seen:
                    seen.add(key)
                    hits.append(h)
    hits = hits[: settings.max_extracts]
    return {
        "hits": hits,
        "trace": [f"run_searches -> {len(hits)} unique hits from {len(queries)} queries"],
    }


# ── ③ extract_candidates (fast model, chunked + parallel screen) ─────────────
def _screen_prompt(hits: list[dict], t: dict, geo: str) -> str:
    joined = "\n\n".join(
        f"[{i}] {h['title']}\n{h['url']}\n{h['content']}" for i, h in enumerate(hits)
    )
    return f"""You are a VC sourcing analyst screening raw search results for founder candidates.

## Investment Thesis
- Industries: {t["industries"]}
- Geography: {t["geo"]}
- Technical focus: {t["keywords"]}

## Task
From the search results below, extract EVERY distinct FOUNDER candidate — a real person building
something aligned with the thesis. Return as many well-supported people as the results contain.

## Rules
1. display_name = the person's real full name when available. If a result only exposes a
   USERNAME/HANDLE or a FIRST NAME (common on GitHub, HN, arXiv, hackathon/event pages), STILL
   extract them — put the handle/first name in display_name, leave first_name/last_name null;
   later research resolves the real name. Only skip results with NO identifiable individual (pure
   company/product/marketing/index pages). NEVER emit a candidate literally named "None".
2. Extract EVERY named individual who is plausibly a builder — INCLUDING multiple co-authors of a
   paper, multiple members of a lab / student-club / org page, and multiple hackathon participants.
   Do NOT collapse a multi-person page to one. Do NOT invent a person or stitch a name onto an
   unrelated handle/company.
3. Geo is a SOFT preference, NOT a hard gate. KEEP people whose location is unknown (set city null —
   research verifies later). DROP someone only with explicit evidence they are clearly OUTSIDE
   {geo} with no tie. Never fabricate a location or emit a person you noted should be dropped.
4. People only — skip pure companies. PREFER pre-founders (students, PhD researchers, hackathon
   participants, club members) with NO company yet — current_company=null is expected and GOOD,
   we want them BEFORE they found. De-prioritize established, well-funded company founders.
5. Merge results about the same person. Capture handles/links present (github, twitter, linkedin,
   website, orcid), occupation, current_company (null if pre-company), why_relevant, source_urls.

## Search Results
{joined}"""


def _extract_chunk(hits: list[dict], t: dict, geo: str) -> list:
    return _llm(CandidateList).invoke(_screen_prompt(hits, t, geo)).candidates


def extract_candidates(state: DiscoveryState) -> dict:
    hits = state["hits"]
    t = state["thesis"]
    geo = ", ".join(t.get("geo") or []) or "any"
    size = settings.extract_chunk_size
    chunks = [hits[i : i + size] for i in range(0, len(hits), size)] or [[]]
    with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
        results = list(ex.map(lambda c: _extract_chunk(c, t, geo), chunks))
    # Merge across chunks, dedup by normalized name (same person can surface in two chunks).
    merged: dict[str, dict] = {}
    for cand_list in results:
        for c in cand_list:
            key = _norm(c.display_name)
            if key and key not in merged:
                merged[key] = c.model_dump()
    cands = list(merged.values())[: settings.max_candidates]
    return {
        "candidates": cands,
        "trace": [f"extract_candidates -> {len(cands)} candidates from {len(chunks)} chunks"],
    }


# ── ④ research_candidates (parallel · recursive · smart-model synthesis) ──────
def _research_context(cand: dict, thesis: dict) -> str:
    geo = ", ".join(thesis.get("geo") or [])
    inds = " ".join(thesis["industries"])
    name = cand["display_name"]
    # Anchor on the candidate's known identifiers so we don't conflate same-named people.
    anchors = " ".join(
        v
        for v in (
            cand.get("github"),
            cand.get("website"),
            cand.get("linkedin"),
            cand.get("current_company"),
        )
        if v
    )
    rounds = [
        f"{name} {cand.get('current_company') or ''} founder {inds}",
        (
            f"{name} {anchors}".strip()
            if anchors
            else f"{name} {geo} LinkedIn GitHub personal website"
        ),
        f"{name} {geo} {inds} hackathon research university founder",
    ][: settings.research_rounds]
    parts = []
    for q in rounds:
        try:
            res = tavily.tavily_search(
                q,
                settings.tavily_api_key,
                max_results=settings.tavily_max_results,
                search_depth="advanced",
                include_raw_content=True,
            )
        except httpx.HTTPError:
            continue
        parts.append(
            "\n\n".join(
                f"{r.get('title')}\n{r.get('url')}\n"
                f"{(r.get('raw_content') or r.get('content') or '')[:1200]}"
                for r in res.get("results", [])
            )
        )
    return "\n\n".join(parts)


def _synthesis_prompt(cand: dict, ctx: str) -> str:
    return f"""You are a VC analyst producing a founder profile from multi-round web research.

## Candidate
{cand}

## Web Research
{ctx}

## Task
Produce a structured founder profile for THIS candidate.

## Requirements
- The research may describe SEVERAL different people who share this name. Include a signal ONLY if
  it is clearly the SAME person as the candidate's known identifiers (github / website / company /
  field). When uncertain whether a result is the same person, EXCLUDE it.
- resolved_name: the person's REAL full name if the candidate name was a username/handle
  (else null).
- education: list of {{school, degree, field, year}}.
- extra_signals: each a DISTINCT public artifact (source, signal_type, canonical_url, title,
  summary, occurred_at as ISO date if visible). Use ONLY URLs that appear above — never invent."""


def _assemble_founder(cand: dict, research: CandidateResearch) -> dict:
    signals: list[dict] = []
    seen: set[str] = set()
    for s in research.extra_signals:
        canon = _canonicalize(s.canonical_url)
        if not canon or canon in seen:
            continue
        seen.add(canon)
        src = _infer_source(
            canon
        )  # always derive from URL — don't trust the LLM's free-form source
        signals.append(
            {
                "source": src,
                "signal_type": s.signal_type,
                "external_id": canon,
                "canonical_url": canon,
                "url": s.canonical_url,
                "content_hash": _content_hash(s.title, s.summary),
                "title": s.title,
                "summary": s.summary,
                "occurred_at": s.occurred_at,
                "source_reliability": SOURCE_RELIABILITY.get(src, 0.4),
                "sources_seen": [src],
            }
        )
    identity = _derive_identity(cand, signals)
    strong = any(identity.get(k) for k in ("github", "linkedin", "website", "orcid", "twitter"))
    for sig in signals:
        sig["resolution_confidence"] = 0.9 if strong else 0.7
        sig["resolution_method"] = "exact_key" if strong else "fuzzy"

    name = cand["display_name"]
    resolved = research.resolved_name
    if resolved and " " in resolved.strip() and " " not in (name or "").strip():
        name = resolved.strip()
    first, last = cand.get("first_name"), cand.get("last_name")
    if not first and not last:
        first, last = _split_name(name)

    n = len(signals)
    disc = min(0.95, 0.4 + 0.1 * n + (0.2 if strong else 0.0))
    status = "candidate" if (strong or n >= 2) else "needs_review"
    return {
        "id": str(uuid.uuid4()),
        "status": status,
        "display_name": name,
        "first_name": first,
        "last_name": last,
        "city": cand.get("city"),
        "occupation": cand.get("occupation"),
        "current_company": cand.get("current_company"),
        "education": [e.model_dump() for e in research.education],
        "identity": identity,
        "discovery_confidence": round(disc, 2),
        "first_discovered_at": datetime.now(UTC).isoformat(),
        "why_relevant": cand.get("why_relevant"),
        "signals": signals,
    }


def _enrich_from_website(cand: dict) -> None:
    """Personal site / portfolio → mine GitHub + socials (people almost always link them).

    Deterministic regex over the fetched page — no LLM. Fills only missing handles.
    """
    site = cand.get("website")
    if not site:
        return
    try:
        data = tavily.tavily_extract([site], settings.tavily_api_key)
    except httpx.HTTPError:
        return
    text = " ".join(r.get("raw_content", "") or "" for r in data.get("results", []))
    if not cand.get("github"):
        m = re.search(r"github\.com/([A-Za-z0-9_.-]+)", text)
        if m and m.group(1).lower() not in ("orgs", "topics", "search", "about", "sponsors"):
            cand["github"] = m.group(1)
    if not cand.get("twitter"):
        m = re.search(r"(?:twitter|x)\.com/([A-Za-z0-9_]+)", text)
        if m and m.group(1).lower() not in ("i", "home", "search", "share", "intent"):
            cand["twitter"] = m.group(1)
    if not cand.get("linkedin"):
        m = re.search(r"linkedin\.com/in/([A-Za-z0-9%-]+)", text)
        if m:
            cand["linkedin"] = f"https://www.linkedin.com/in/{m.group(1)}"


def _profile_one(cand: dict, thesis: dict) -> dict:
    _enrich_from_website(cand)  # portfolio → GitHub/socials before we resolve identity
    ctx = _research_context(cand, thesis)
    research = _llm(CandidateResearch, smart=True).invoke(_synthesis_prompt(cand, ctx))
    return _assemble_founder(cand, research)


def research_candidates(state: DiscoveryState) -> dict:
    raw = state["candidates"]
    cands = [c for c in raw if _worth_researching(c)]  # cheap gate before expensive gpt-5.4
    thesis = state["thesis"]
    with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
        founders = list(ex.map(lambda c: _profile_one(c, thesis), cands))
    return {
        "founders": founders,
        "trace": [
            f"research_candidates -> {len(founders)} founders "
            f"({len(raw) - len(cands)} gated out; gpt-5.4 synthesis, "
            f"{settings.research_rounds} rounds each, parallel)"
        ],
    }


# ── ⑤ finalize ───────────────────────────────────────────────────────────────
def finalize(state: DiscoveryState) -> dict:
    founders = state.get("founders", [])
    stats = {
        "queries_run": len(state.get("queries", [])),
        "raw_hits": len(state.get("hits", [])),
        "candidates_extracted": len(state.get("candidates", [])),
        "new_founders": len(founders),
        "new_signals": sum(len(f["signals"]) for f in founders),
        "needs_review": sum(1 for f in founders if f["status"] == "needs_review"),
    }
    return {"stats": stats, "trace": [f"finalize -> {stats}"]}


def build_discovery_graph():
    g = StateGraph(DiscoveryState)
    g.add_node("plan_searches", plan_searches)
    g.add_node("run_searches", run_searches)
    g.add_node("extract_candidates", extract_candidates)
    g.add_node("research_candidates", research_candidates)
    g.add_node("finalize", finalize)
    g.add_edge(START, "plan_searches")
    g.add_edge("plan_searches", "run_searches")
    g.add_edge("run_searches", "extract_candidates")
    g.add_edge("extract_candidates", "research_candidates")
    g.add_edge("research_candidates", "finalize")
    g.add_edge("finalize", END)
    return g.compile()
