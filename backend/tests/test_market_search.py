"""The market graph must use the same search-provider policy as sourcing.

`app/market/graph._search_one` called Tavily directly and swallowed every httpx error into an
empty list. With Tavily disabled (settings.tavily_enabled = False) that meant *every* market
query returned nothing, and the graph reported it as "no market evidence found" — a persisted
market axis with all-gap figures and a low confidence — rather than "the search provider is
not answering". A dead dependency looked like a real research result.

Sourcing already solved this in app/sourcing/fetchers.tavily_fetch: honour `tavily_enabled`,
fall back to Responses on transient provider failure, and re-raise anything that is our own bug
(401 bad key, 400 malformed query) instead of quietly paying a second provider for every query.
The market path now follows the same policy.
"""

import httpx
import pytest

from app.market import graph as market_graph


def _response(status: int) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("POST", "https://api.tavily.com/search"))


def test_disabled_tavily_routes_to_responses(monkeypatch) -> None:
    """The regression: with Tavily off, queries must reach the fallback, not return empty."""
    monkeypatch.setattr(market_graph.settings, "tavily_enabled", False)

    def boom(*_a, **_k):
        raise AssertionError("Tavily must not be called while disabled")

    monkeypatch.setattr(market_graph.tavily, "tavily_search", boom)
    monkeypatch.setattr(
        market_graph,
        "responses_web_search",
        lambda _q, _c: [{"title": "T", "url": "https://e.test/a", "content": "body"}],
    )

    hits = market_graph._search_one({"query": "tam for x", "subgoal": "sizing"})
    assert hits == [
        {"subgoal": "sizing", "title": "T", "url": "https://e.test/a", "content": "body"}
    ]


def test_transient_tavily_failure_degrades_to_responses(monkeypatch) -> None:
    monkeypatch.setattr(market_graph.settings, "tavily_enabled", True)

    def rate_limited(*_a, **_k):
        raise httpx.HTTPStatusError("429", request=_response(429).request, response=_response(429))

    monkeypatch.setattr(market_graph.tavily, "tavily_search", rate_limited)
    monkeypatch.setattr(
        market_graph,
        "responses_web_search",
        lambda _q, _c: [{"title": "T", "url": "https://e.test/b", "content": "body"}],
    )

    hits = market_graph._search_one({"query": "tam for x", "subgoal": "kpi"})
    assert [h["url"] for h in hits] == ["https://e.test/b"]
    assert hits[0]["subgoal"] == "kpi"


def test_bad_api_key_raises_instead_of_silently_returning_nothing(monkeypatch) -> None:
    """A 401 is our bug. Crashing beats reporting an empty market as a research finding."""
    monkeypatch.setattr(market_graph.settings, "tavily_enabled", True)

    def unauthorized(*_a, **_k):
        raise httpx.HTTPStatusError("401", request=_response(401).request, response=_response(401))

    monkeypatch.setattr(market_graph.tavily, "tavily_search", unauthorized)
    monkeypatch.setattr(
        market_graph, "responses_web_search", lambda _q, _c: pytest.fail("must not fall back")
    )

    with pytest.raises(httpx.HTTPStatusError):
        market_graph._search_one({"query": "tam for x", "subgoal": "sizing"})


def test_connection_error_degrades_to_responses(monkeypatch) -> None:
    monkeypatch.setattr(market_graph.settings, "tavily_enabled", True)

    def dropped(*_a, **_k):
        raise httpx.ConnectError("connection reset")

    monkeypatch.setattr(market_graph.tavily, "tavily_search", dropped)
    monkeypatch.setattr(
        market_graph,
        "responses_web_search",
        lambda _q, _c: [{"title": "T", "url": "https://e.test/c", "content": "body"}],
    )

    hits = market_graph._search_one({"query": "q", "subgoal": "competition"})
    assert [h["url"] for h in hits] == ["https://e.test/c"]
