"""Pure unit tests for native fetchers — normalizers, keyword distillation, fallback. No network."""

import httpx
import pytest

from app.sourcing import fetchers
from app.sourcing.fetchers import (
    _arxiv_entries,
    _arxiv_hit,
    _clean_hn_text,
    _github_hit,
    _hn_hit,
    _keywords,
    get_fetcher,
    with_tavily_fallback,
)

CHANNEL = {"name": "test-channel", "domain": "example.com"}


# ── keyword distillation ─────────────────────────────────────────────────────


def test_keywords_strips_stopwords_and_caps():
    q = "students building AI infrastructure tools at Berlin hackathons"
    assert _keywords(q, 4) == ["ai", "infrastructure", "tools", "berlin"]


def test_keywords_dedupes_and_keeps_tech_tokens():
    q = "c++ and C++ devs building llm.c forks"
    assert _keywords(q, 5) == ["c++", "devs", "llm.c", "forks"]


def test_keywords_empty_query():
    assert _keywords("the of and", 4) == []


# ── registry ─────────────────────────────────────────────────────────────────


def test_native_fetchers_registered():
    for name in ("github", "arxiv", "hn"):
        assert get_fetcher(name) is not get_fetcher("tavily")


def test_unknown_fetcher_falls_back_to_tavily():
    assert get_fetcher("nope") is get_fetcher("tavily")
    assert get_fetcher(None) is get_fetcher("tavily")


# ── tavily fallback wrapper ──────────────────────────────────────────────────


def _patch_tavily(monkeypatch, sentinel):
    calls = []

    def fake(query, channel):
        calls.append(query)
        return sentinel

    monkeypatch.setattr(fetchers, "tavily_fetch", fake)
    return calls


def test_fallback_on_http_error(monkeypatch):
    calls = _patch_tavily(monkeypatch, [{"url": "fallback"}])

    @with_tavily_fallback
    def broken(query, channel):
        raise httpx.ConnectTimeout("down")

    assert broken("q", CHANNEL) == [{"url": "fallback"}]
    assert calls == ["q"]


def test_fallback_on_zero_hits(monkeypatch):
    calls = _patch_tavily(monkeypatch, [{"url": "fallback"}])

    @with_tavily_fallback
    def empty(query, channel):
        return []

    assert empty("q", CHANNEL) == [{"url": "fallback"}]
    assert calls == ["q"]


def test_no_fallback_when_native_delivers(monkeypatch):
    calls = _patch_tavily(monkeypatch, [{"url": "fallback"}])

    @with_tavily_fallback
    def good(query, channel):
        return [{"url": "native"}]

    assert good("q", CHANNEL) == [{"url": "native"}]
    assert calls == []


def test_fallback_does_not_swallow_contract_bugs(monkeypatch):
    _patch_tavily(monkeypatch, [])

    @with_tavily_fallback
    def buggy(query, channel):
        raise KeyError("items")  # malformed payload = bug, must crash

    with pytest.raises(KeyError):
        buggy("q", CHANNEL)


# ── github normalization ─────────────────────────────────────────────────────


def test_github_hit_shape():
    item = {
        "full_name": "janedoe/vector-db",
        "html_url": "https://github.com/janedoe/vector-db",
        "description": "Tiny vector database",
        "language": "Rust",
        "stargazers_count": 412,
        "forks_count": 30,
        "created_at": "2026-05-01T00:00:00Z",
        "pushed_at": "2026-07-15T00:00:00Z",
        "topics": ["ai", "database"],
        "owner": {"login": "janedoe"},
    }
    hit = _github_hit(item, CHANNEL)
    assert hit["channel"] == "test-channel"
    assert hit["url"] == "https://github.com/janedoe/vector-db"
    assert "GitHub repo: janedoe/vector-db" == hit["title"]
    # owner profile URL present -> identity mining resolves by strong ID
    assert "https://github.com/janedoe" in hit["content"]
    assert "Stars: 412" in hit["content"]


def test_github_hit_null_description_and_language():
    item = {
        "full_name": "x/y",
        "html_url": "https://github.com/x/y",
        "description": None,
        "language": None,
        "stargazers_count": 0,
        "forks_count": 0,
        "created_at": "2026-01-01T00:00:00Z",
        "pushed_at": "2026-01-02T00:00:00Z",
        "topics": [],
        "owner": {"login": "x"},
    }
    hit = _github_hit(item, CHANNEL)
    assert "Language: n/a" in hit["content"]


# ── arxiv normalization ──────────────────────────────────────────────────────

ARXIV_ATOM = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2607.01234v1</id>
    <title>Efficient  Sparse
      Attention</title>
    <summary>We propose  a method.</summary>
    <published>2026-07-01T00:00:00Z</published>
    <author><name>Jane Doe</name></author>
    <author><name>John Smith</name></author>
  </entry>
</feed>"""


def test_arxiv_entries_and_hit():
    entries = _arxiv_entries(ARXIV_ATOM)
    assert len(entries) == 1
    hit = _arxiv_hit(entries[0], CHANNEL)
    assert hit["url"] == "http://arxiv.org/abs/2607.01234v1"
    assert hit["title"] == "arXiv paper: Efficient Sparse Attention"  # whitespace collapsed
    assert "Authors: Jane Doe, John Smith" in hit["content"]
    assert "We propose a method." in hit["content"]


# ── hn normalization ─────────────────────────────────────────────────────────


def test_hn_hit_shape():
    h = {
        "objectID": "41234567",
        "title": "Show HN: I built a GPU cost tracker",
        "url": "https://gputracker.dev",
        "author": "janedoe",
        "points": 120,
        "num_comments": 45,
        "created_at": "2026-07-10T12:00:00Z",
        "story_text": None,
    }
    hit = _hn_hit(h, CHANNEL)
    assert hit["url"] == "https://news.ycombinator.com/item?id=41234567"
    assert hit["title"] == "Show HN: I built a GPU cost tracker"
    assert "https://news.ycombinator.com/user?id=janedoe" in hit["content"]
    assert "Product URL: https://gputracker.dev" in hit["content"]


def test_hn_hit_self_post_without_url():
    # Algolia OMITS url/story_text keys on some records (seen live) — no KeyError allowed.
    h = {
        "objectID": "1",
        "title": "Show HN: text-only launch",
        "author": "x",
        "points": 1,
        "num_comments": 0,
        "created_at": "2026-07-10T12:00:00Z",
        "story_text": "Body text here",
    }
    hit = _hn_hit(h, CHANNEL)
    assert "Product URL" not in hit["content"]
    assert "Body text here" in hit["content"]


def test_clean_hn_text_unescapes_and_keeps_link_targets():
    raw = (
        'Hey HN &#x27;team&#x27;, see <a href="https:&#x2F;&#x2F;armalo.ai" '
        'rel="nofollow">armalo.ai</a><p>Second paragraph</p>'
    )
    cleaned = _clean_hn_text(raw)
    assert "Hey HN 'team'" in cleaned
    assert "https://armalo.ai" in cleaned
    assert "<" not in cleaned and "&#x27;" not in cleaned
    assert "Second paragraph" in cleaned
