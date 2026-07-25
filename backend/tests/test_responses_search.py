"""Unit tests for Responses web-search normalization; no OpenAI network calls."""

import json
from types import SimpleNamespace

from app.sourcing import responses_search


def test_responses_web_search_returns_normalized_source_artifacts(monkeypatch):
    class FakeResponses:
        def create(self, **kwargs):
            assert kwargs["tools"][0]["type"] == "web_search"
            assert kwargs["tools"][0]["filters"] == {"allowed_domains": ["example.com"]}
            return SimpleNamespace(
                output_text=json.dumps(
                    {
                        "results": [
                            {
                                "title": "Winning team",
                                "url": "https://example.com/results",
                                "content": "Ada and Grace won the hackathon.",
                            }
                        ]
                    }
                )
            )

    monkeypatch.setattr(
        responses_search, "OpenAI", lambda **kwargs: SimpleNamespace(responses=FakeResponses())
    )
    monkeypatch.setattr(responses_search.settings, "openai_api_key", "test-key")

    assert responses_search.responses_web_search(
        "hackathon winners", {"name": "events", "domain": "example.com"}
    ) == [
        {
            "channel": "events",
            "title": "Winning team",
            "url": "https://example.com/results",
            "content": "Ada and Grace won the hackathon.",
        }
    ]


def test_responses_web_search_discards_invalid_urls(monkeypatch):
    class FakeResponses:
        def create(self, **kwargs):
            return SimpleNamespace(
                output_text='{"results": [{"title": "Bad", "url": "not-a-url", "content": "x"}]}'
            )

    monkeypatch.setattr(
        responses_search, "OpenAI", lambda **kwargs: SimpleNamespace(responses=FakeResponses())
    )
    monkeypatch.setattr(responses_search.settings, "openai_api_key", "test-key")

    assert responses_search.responses_web_search("query", {"name": "web"}) == []
