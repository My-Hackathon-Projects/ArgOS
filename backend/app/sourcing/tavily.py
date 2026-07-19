"""Thin Tavily REST client (httpx). No extra dependency, full control over params."""

import httpx

_SEARCH_URL = "https://api.tavily.com/search"


def tavily_search(
    query: str,
    api_key: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
) -> dict:
    payload: dict = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_raw_content": False,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    resp = httpx.post(_SEARCH_URL, json=payload, timeout=45)
    resp.raise_for_status()
    return resp.json()
