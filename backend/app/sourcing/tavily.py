"""Thin Tavily REST client (httpx). No extra dependency, full control over params."""

import httpx

_SEARCH_URL = "https://api.tavily.com/search"


def tavily_search(
    query: str,
    api_key: str,
    max_results: int = 5,
    include_domains: list[str] | None = None,
    search_depth: str = "basic",
    include_raw_content: bool = False,
) -> dict:
    payload: dict = {
        "api_key": api_key,
        "query": query,
        "max_results": max_results,
        "search_depth": search_depth,
        "include_raw_content": include_raw_content,
    }
    if include_domains:
        payload["include_domains"] = include_domains
    resp = httpx.post(_SEARCH_URL, json=payload, timeout=45)
    resp.raise_for_status()
    return resp.json()


_EXTRACT_URL = "https://api.tavily.com/extract"


def tavily_extract(urls: list[str], api_key: str) -> dict:
    """Full page content for given URLs — used to mine a personal site for GitHub/social links."""
    resp = httpx.post(_EXTRACT_URL, json={"api_key": api_key, "urls": urls}, timeout=45)
    resp.raise_for_status()
    return resp.json()
