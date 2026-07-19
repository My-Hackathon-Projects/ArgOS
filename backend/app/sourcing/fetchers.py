"""Pluggable per-channel fetchers — the extensibility seam for adding new sources.

The discovery graph never hardcodes a source. Each channel selects a fetcher by name
(default ``"tavily"``); to add a brand-new source (a company registry, a grants feed, ...) you:

  1. write ``def my_fetch(query, channel) -> list[hit]``
  2. decorate it ``@register("my_source")``
  3. set ``"fetcher": "my_source"`` on the channel (seeds.py or the sourcing_channel table)

No graph/persist changes needed — hits flow into the same screen → research → resolve → dedup
pipeline. Contract: ``fetch(query: str, channel: dict) -> list[hit]`` where
``hit = {"channel": str, "title": str, "url": str, "content": str}``.

Native (keyless) fetchers: ``github`` (repo search API), ``arxiv`` (export API, Atom),
``hn`` (Algolia Show HN). Each is wrapped in ``with_tavily_fallback`` so a network failure
or an empty native result degrades to the default domain-scoped web search — native APIs
can only ADD richness, never lose the coverage the tavily path already had. Planner queries
are natural-language (tuned for neural search); ``_keywords`` distills them for the
keyword-matching native APIs.
"""

import functools
import html
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx

from app.config import settings
from app.sourcing import tavily

Fetcher = Callable[[str, dict], list[dict]]
_REGISTRY: dict[str, Fetcher] = {}


def register(name: str) -> Callable[[Fetcher], Fetcher]:
    def deco(fn: Fetcher) -> Fetcher:
        _REGISTRY[name] = fn
        return fn

    return deco


def get_fetcher(name: str | None) -> Fetcher:
    """Resolve a channel's fetcher by name, falling back to the default web search."""
    return _REGISTRY.get(name or "tavily", _REGISTRY["tavily"])


@register("tavily")
def tavily_fetch(query: str, channel: dict) -> list[dict]:
    """Default: neural web search scoped to the channel's domain, with full page content."""
    domains = [channel["domain"]] if channel.get("domain") else None
    try:
        res = tavily.tavily_search(
            query,
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
            "channel": channel.get("name"),
            "title": r.get("title"),
            "url": r.get("url"),
            # raw_content (fuller page) surfaces author/member/participant names snippets miss
            "content": (r.get("raw_content") or r.get("content") or "")[
                : settings.hit_content_chars
            ],
        }
        for r in res.get("results", [])
    ]


# ── Native keyless fetchers ──────────────────────────────────────────────────

# Query-planner output is NL prose; native APIs match keywords. Strip filler, keep
# discriminative terms. Includes sourcing-prompt boilerplate (founders, students, ...)
# that would dilute a keyword search.
_STOPWORDS = frozenset(
    """a an and are at based best building builders by early for from in is new of on or
    people projects recent stage students that the their to top who winners with working
    founders founder developers builder participants authors startup startups""".split()
)

GITHUB_PUSHED_WITHIN_DAYS = 120  # bias to actively-built repos (we source people, not archives)


def _keywords(query: str, limit: int) -> list[str]:
    words = re.findall(r"[a-z0-9][a-z0-9+#.-]*", query.lower())
    out: list[str] = []
    for w in words:
        if len(w) < 2 or w in _STOPWORDS or w in out:
            continue
        out.append(w)
    return out[:limit]


def with_tavily_fallback(fn: Fetcher) -> Fetcher:
    """Degrade to the default web search on network failure or zero native hits.

    Only ``httpx.HTTPError`` (timeouts, 4xx/5xx, rate limits) triggers fallback —
    a malformed payload is a contract bug and must crash (fail fast), not hide.
    """

    @functools.wraps(fn)
    def wrapped(query: str, channel: dict) -> list[dict]:
        try:
            hits = fn(query, channel)
        except httpx.HTTPError:
            hits = []
        return hits or tavily_fetch(query, channel)

    return wrapped


@register("github")
@with_tavily_fallback
def github_fetch(query: str, channel: dict) -> list[dict]:
    """GitHub repo search: recently-pushed repos + owner handle (a strong resolution ID).

    Keyless (10 req/min unauthenticated); set GITHUB_TOKEN to raise the limit.
    """
    kws = _keywords(query, 4)
    if not kws:
        return []
    since = (datetime.now(UTC) - timedelta(days=GITHUB_PUSHED_WITHIN_DAYS)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "argos-sourcing"}
    if settings.github_token:
        headers["Authorization"] = f"Bearer {settings.github_token}"
    resp = httpx.get(
        "https://api.github.com/search/repositories",
        params={
            "q": f"{' '.join(kws)} pushed:>{since}",
            "sort": "updated",
            "per_page": settings.native_max_results,
        },
        headers=headers,
        timeout=15,
    )
    resp.raise_for_status()
    return [_github_hit(item, channel) for item in resp.json()["items"]]


def _github_hit(item: dict, channel: dict) -> dict:
    # Owner handle spelled out as a profile URL: downstream identity mining regexes +
    # the extract LLM both pick it up, so founders resolve by strong ID, not name.
    owner = item["owner"]["login"]
    content = "\n".join(
        [
            item["description"] or "",
            f"Owner GitHub handle: {owner} (https://github.com/{owner})",
            f"Language: {item['language'] or 'n/a'}",
            f"Stars: {item['stargazers_count']}, forks: {item['forks_count']}",
            f"Created: {item['created_at']}, last push: {item['pushed_at']}",
            f"Topics: {', '.join(item['topics'])}",
        ]
    )
    return {
        "channel": channel.get("name"),
        "title": f"GitHub repo: {item['full_name']}",
        "url": item["html_url"],
        "content": content[: settings.hit_content_chars],
    }


_ATOM = "{http://www.w3.org/2005/Atom}"


@register("arxiv")
@with_tavily_fallback
def arxiv_fetch(query: str, channel: dict) -> list[dict]:
    """arXiv export API (keyless, Atom XML): freshest papers matching the thesis keywords."""
    kws = _keywords(query, 3)
    if not kws:
        return []
    resp = httpx.get(
        "https://export.arxiv.org/api/query",
        params={
            "search_query": " AND ".join(f"all:{k}" for k in kws),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": settings.native_max_results,
        },
        headers={"User-Agent": "argos-sourcing"},
        timeout=20,
    )
    resp.raise_for_status()
    return [_arxiv_hit(e, channel) for e in _arxiv_entries(resp.text)]


def _arxiv_entries(xml_text: str) -> list[dict]:
    root = ET.fromstring(xml_text)
    return [
        {
            "id": e.findtext(f"{_ATOM}id"),
            "title": " ".join((e.findtext(f"{_ATOM}title") or "").split()),
            "summary": " ".join((e.findtext(f"{_ATOM}summary") or "").split()),
            "published": e.findtext(f"{_ATOM}published"),
            "authors": [a.findtext(f"{_ATOM}name") for a in e.findall(f"{_ATOM}author")],
        }
        for e in root.findall(f"{_ATOM}entry")
    ]


def _arxiv_hit(entry: dict, channel: dict) -> dict:
    content = "\n".join(
        [
            f"Authors: {', '.join(entry['authors'])}",
            f"Published: {entry['published']}",
            entry["summary"],
        ]
    )
    return {
        "channel": channel.get("name"),
        "title": f"arXiv paper: {entry['title']}",
        "url": entry["id"],  # abs page — canonical, dedup-stable
        "content": content[: settings.hit_content_chars],
    }


@register("hn")
@with_tavily_fallback
def hn_fetch(query: str, channel: dict) -> list[dict]:
    """HN Algolia API (keyless): Show HN launches — builders shipping, pre-fundraise."""
    kws = _keywords(query, 4)
    if not kws:
        return []
    resp = httpx.get(
        "https://hn.algolia.com/api/v1/search",
        params={
            "query": " ".join(kws),
            "tags": "show_hn",
            "hitsPerPage": settings.native_max_results,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return [_hn_hit(h, channel) for h in resp.json()["hits"]]


def _clean_hn_text(text: str) -> str:
    """story_text is HTML-escaped with markup; keep link targets, drop tags."""
    text = html.unescape(text)
    text = re.sub(r'<a[^>]+href="([^"]+)"[^>]*>.*?</a>', r"\1", text, flags=re.S)
    text = text.replace("<p>", "\n")
    return re.sub(r"<[^>]+>", " ", text).strip()


def _hn_hit(h: dict, channel: dict) -> dict:
    author = h["author"]
    # url + story_text are omitted (not null) on some records — verified live 2026-07-19.
    product_url = h.get("url")
    parts = [
        f"Show HN by {author} (https://news.ycombinator.com/user?id={author})",
        f"Product URL: {product_url}" if product_url else "",
        f"Points: {h['points']}, comments: {h['num_comments']}",
        f"Posted: {h['created_at']}",
        _clean_hn_text(h.get("story_text") or ""),
    ]
    return {
        "channel": channel.get("name"),
        "title": h["title"],
        # HN item page as the signal URL (stable id for dedup); product URL in content
        # so per-founder research rounds can follow it.
        "url": f"https://news.ycombinator.com/item?id={h['objectID']}",
        "content": "\n".join(p for p in parts if p)[: settings.hit_content_chars],
    }
