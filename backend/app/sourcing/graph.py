"""Discovery graph (Q10 blueprint).

Nodes:  plan_searches → run_searches → extract_candidates → research_candidates → finalize
Seeds (app/sourcing/seeds.py) drive the channels; the thesis rides in every node.
finalize hands back an in-memory delivery; persistence is a separate single-writer step.
Auto-traced to LangSmith when LANGSMITH_TRACING=true.
"""

import hashlib
import operator
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated, TypedDict
from urllib.parse import urlsplit, urlunsplit

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


def _llm(schema):
    llm = ChatOpenAI(model=settings.model_fast, api_key=settings.openai_api_key)
    return llm.with_structured_output(schema)


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


def _derive_identity(cand: dict, signals: list[dict]) -> dict:
    """Fill identity handles from the candidate + its signal URLs (powers strong-id resolution)."""
    ident = {k: cand.get(k) for k in ("github", "twitter", "linkedin", "website", "orcid")}
    for s in signals:
        url = s["canonical_url"]
        low = url.lower()
        if not ident["github"] and "github.com/" in low:
            m = re.search(r"github\.com/([A-Za-z0-9-]+)", url)
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
    return ident


# ── ① plan_searches ──────────────────────────────────────────────────────────
def plan_searches(state: DiscoveryState) -> dict:
    t = state["thesis"]
    channels = enabled_channels()
    desc = "\n".join(
        f"- {c['name']} (type={c['type']}, domain={c['domain'] or 'open web'})" for c in channels
    )
    prompt = (
        "You are a VC sourcing agent. Investment thesis:\n"
        f"industries={t['industries']} geo={t['geo']} stage={t['stage']}\n"
        f"keywords={t['keywords']} founder_preferences={t['founder_preferences']}\n\n"
        f"Seed channels we monitor:\n{desc}\n\n"
        "For EACH channel, write ONE focused search query to DISCOVER early / pre-seed FOUNDERS "
        "(people building something, not just companies) matching this thesis. Respect the geography. "
        "Set `domain` to the channel's domain (or null for open web) and `channel` to its name."
    )
    plan = _llm(SearchPlan).invoke(prompt)
    queries = [q.model_dump() for q in plan.queries][: settings.max_search_queries]
    return {
        "queries": queries,
        "trace": [f"plan_searches → {len(queries)} queries over {len(channels)} seed channels"],
    }


# ── ② run_searches ───────────────────────────────────────────────────────────
def run_searches(state: DiscoveryState) -> dict:
    hits: list[dict] = []
    seen: set[str] = set()
    for q in state["queries"]:
        domains = [q["domain"]] if q.get("domain") else None
        res = tavily.tavily_search(
            q["query"],
            settings.tavily_api_key,
            max_results=settings.tavily_max_results,
            include_domains=domains,
        )
        for r in res.get("results", []):
            url = r.get("url")
            if url and url not in seen:  # in-run frontier: skip URLs already seen
                seen.add(url)
                hits.append(
                    {
                        "channel": q.get("channel"),
                        "query": q["query"],
                        "title": r.get("title"),
                        "url": url,
                        "content": (r.get("content") or "")[:1500],
                    }
                )
        if len(hits) >= settings.max_extracts:
            break
    return {"hits": hits, "trace": [f"run_searches → {len(hits)} unique hits"]}


# ── ③ extract_candidates ─────────────────────────────────────────────────────
def extract_candidates(state: DiscoveryState) -> dict:
    hits = state["hits"]
    joined = "\n\n".join(
        f"[{i}] {h['title']}\n{h['url']}\n{h['content']}" for i, h in enumerate(hits)
    )
    t = state["thesis"]
    prompt = (
        f"From these search results, extract EVERY distinct FOUNDER candidate (a real person building "
        f"something) relevant to thesis industries={t['industries']}, keywords={t['keywords']}, geo={t['geo']}.\n"
        "Return as many well-supported people as the results contain — do not stop at one. "
        "Merge results about the same person into one candidate. People only, not companies. "
        "Capture any handles/links present (github, twitter, linkedin, website, orcid), city, occupation, "
        "current_company (null if pre-company), why_relevant, and the source_urls that support them.\n\n"
        f"RESULTS:\n{joined}"
    )
    cl = _llm(CandidateList).invoke(prompt)
    cands = [c.model_dump() for c in cl.candidates][: settings.max_candidates]
    return {"candidates": cands, "trace": [f"extract_candidates → {len(cands)} candidates"]}


# ── ④ research_candidates (the reusable persona-profiling core) ───────────────
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
    n = len(signals)
    disc = min(0.95, 0.4 + 0.1 * n + (0.2 if strong else 0.0))
    status = "candidate" if (strong or n >= 2) else "needs_review"
    return {
        "id": str(uuid.uuid4()),
        "status": status,
        "display_name": cand["display_name"],
        "first_name": cand.get("first_name"),
        "last_name": cand.get("last_name"),
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


def research_candidates(state: DiscoveryState) -> dict:
    t = state["thesis"]
    founders = []
    for cand in state["candidates"]:
        follow_up = f"{cand['display_name']} {cand.get('current_company') or ''} founder {' '.join(t['industries'])}"
        res = tavily.tavily_search(
            follow_up, settings.tavily_api_key, max_results=settings.tavily_max_results
        )
        ctx = "\n\n".join(
            f"{r.get('title')}\n{r.get('url')}\n{(r.get('content') or '')[:800]}"
            for r in res.get("results", [])
        )
        prompt = (
            f"Profile this founder for a VC. Candidate:\n{cand}\n\nExtra web context:\n{ctx}\n\n"
            "Return education and extra_signals (each a DISTINCT public artifact: source, signal_type, "
            "canonical_url, title, summary, occurred_at as ISO date if visible). "
            "Only use URLs that actually appear above — never invent."
        )
        research = _llm(CandidateResearch).invoke(prompt)
        founders.append(_assemble_founder(cand, research))
    return {
        "founders": founders,
        "trace": [f"research_candidates → {len(founders)} founders profiled"],
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
    return {"stats": stats, "trace": [f"finalize → {stats}"]}


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
