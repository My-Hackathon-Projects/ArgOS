"""Pluggable per-channel fetchers — the extensibility seam for adding new sources.

The discovery graph never hardcodes a source. Each channel selects a fetcher by name
(default ``"tavily"``); to add a brand-new source (a real arXiv/GitHub API, a company
registry, a grants feed, ...) you:

  1. write ``def my_fetch(query, channel) -> list[hit]``
  2. decorate it ``@register("my_source")``
  3. set ``"fetcher": "my_source"`` on the channel (seeds.py or the sourcing_channel table)

No graph/persist changes needed — hits flow into the same screen → research → resolve → dedup
pipeline. Contract: ``fetch(query: str, channel: dict) -> list[hit]`` where
``hit = {"channel": str, "title": str, "url": str, "content": str}``.
"""

from collections.abc import Callable

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
