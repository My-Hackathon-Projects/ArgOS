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
For EACH channel, write {settings.queries_per_channel} focused, executable search queries to
discover EARLY-STAGE FOUNDERS — real people actively building (code, launches, papers, hackathons,
open source), not companies.

## Requirements
1. Geographic bias: every query MUST include a geo or institutional anchor from the thesis
   (geography: {geo}; target schools: {schools}) so results surface LOCAL builders,
   not global feeds.
2. Prioritize founders over companies — look for signals of active building.
3. Target EARLY people matching the founder profile: {signals}. Favor members of the target
   communities ({communities}) and students/researchers at the target schools ({schools}).
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
        )
    except httpx.HTTPError:
        return []  # one flaky query must not sink a 16-query fan-out (narrow, not silent)
    return [
        {
            "channel": q.get("channel"),
            "title": r.get("title"),
            "url": r.get("url"),
            "content": (r.get("content") or "")[:1500],
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
                if h["url"] and h["url"] not in seen:  # frontier: skip URLs already seen this run
                    seen.add(h["url"])
                    hits.append(h)
    hits = hits[: settings.max_extracts]
    return {
        "hits": hits,
        "trace": [f"run_searches -> {len(hits)} unique hits from {len(queries)} queries"],
    }


# ── ③ extract_candidates (fast model, structured screen) ─────────────────────
def extract_candidates(state: DiscoveryState) -> dict:
    hits = state["hits"]
    joined = "\n\n".join(
        f"[{i}] {h['title']}\n{h['url']}\n{h['content']}" for i, h in enumerate(hits)
    )
    t = state["thesis"]
    geo = ", ".join(t.get("geo") or []) or "any"
    prompt = f"""You are a VC sourcing analyst screening raw search results for founder candidates.

## Investment Thesis
- Industries: {t["industries"]}
- Geography: {t["geo"]}
- Technical focus: {t["keywords"]}

## Task
From the search results below, extract EVERY distinct FOUNDER candidate — a real person building
something aligned with the thesis. Return as many well-supported people as the results contain.

## Rules
1. display_name MUST be the person's real full name (first AND last). NEVER a username, handle,
   single first name, or company name. Skip anyone you cannot tie to a real full name.
2. One real person per candidate. Do NOT invent multiple candidates from a repo's contributor
   list, commenters, or org members — only the actual founder(s) / creator(s).
3. HARD geo filter — include a person ONLY if the results give evidence they are based in or
   clearly tied to {geo}. Set `city` ONLY from explicit evidence; NEVER assume or fabricate the
   target geography. If location is unknown or clearly outside {geo}, DROP the person.
4. People only — skip pure companies. Prefer EARLY builders (students, hackathon participants,
   stealth) over established, well-funded company founders.
5. Merge results about the same person. Capture handles/links present (github, twitter, linkedin,
   website, orcid), occupation, current_company (null if pre-company), why_relevant, source_urls.

## Search Results
{joined}"""
    cl = _llm(CandidateList).invoke(prompt)
    cands = [c.model_dump() for c in cl.candidates][: settings.max_candidates]
    return {"candidates": cands, "trace": [f"extract_candidates -> {len(cands)} candidates"]}


# ── ④ research_candidates (parallel · recursive · smart-model synthesis) ──────
def _research_context(cand: dict, thesis: dict) -> str:
    geo = ", ".join(thesis.get("geo") or [])
    inds = " ".join(thesis["industries"])
    prefs = thesis.get("founder_preferences") or {}
    schools = " OR ".join((prefs.get("schools") or [])[:3])
    round2 = f"{cand['display_name']} {geo} founder LinkedIn OR GitHub OR hackathon OR university"
    if schools:
        round2 += f" OR {schools}"
    rounds = [
        f"{cand['display_name']} {cand.get('current_company') or ''} founder {inds}",
        round2,
    ][: settings.research_rounds]
    parts = []
    for q in rounds:
        try:
            res = tavily.tavily_search(
                q, settings.tavily_api_key, max_results=settings.tavily_max_results
            )
        except httpx.HTTPError:
            continue
        parts.append(
            "\n\n".join(
                f"{r.get('title')}\n{r.get('url')}\n{(r.get('content') or '')[:800]}"
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
Produce a structured founder profile.

## Requirements
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


def _profile_one(cand: dict, thesis: dict) -> dict:
    ctx = _research_context(cand, thesis)
    research = _llm(CandidateResearch, smart=True).invoke(_synthesis_prompt(cand, ctx))
    return _assemble_founder(cand, research)


def research_candidates(state: DiscoveryState) -> dict:
    cands = state["candidates"]
    thesis = state["thesis"]
    with ThreadPoolExecutor(max_workers=settings.max_workers) as ex:
        founders = list(ex.map(lambda c: _profile_one(c, thesis), cands))
    return {
        "founders": founders,
        "trace": [
            f"research_candidates -> {len(founders)} founders "
            f"(gpt-5.4 synthesis, {settings.research_rounds} rounds each, parallel)"
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
