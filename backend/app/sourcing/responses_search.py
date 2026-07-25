"""OpenAI Responses web-search fallback for outbound sourcing.

Tavily remains the primary provider.  This adapter is deliberately shaped like a
fetcher so callers continue to receive ordinary source artifacts rather than an
LLM profile: ``title``, canonical source ``url``, and a short source-derived
excerpt for the existing extraction pipeline.
"""

import json
import threading
from urllib.parse import urlsplit

import httpx
from openai import APIError, OpenAI
from openai.types.responses import WebSearchToolParam

from app.config import settings

_budget_lock = threading.Lock()
_calls_used = 0


def reset_search_budget() -> None:
    """Start a fresh per-run allowance. Called once at the top of a sourcing run."""
    global _calls_used
    with _budget_lock:
        _calls_used = 0
        _failures.clear()


def search_budget_used() -> int:
    with _budget_lock:
        return _calls_used


def _claim_budget() -> bool:
    """Reserve one paid search, or refuse once the run's ceiling is reached."""
    global _calls_used
    with _budget_lock:
        if _calls_used >= settings.responses_search_max_calls:
            return False
        _calls_used += 1
        return True


_failures: list[str] = []


def _record_failure(message: str) -> None:
    with _budget_lock:
        _failures.append(message[:200])


def search_failures() -> list[str]:
    """Provider errors swallowed during the run, so a degraded run is never silent."""
    with _budget_lock:
        return list(_failures)


_RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "url": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["title", "url", "content"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["results"],
    "additionalProperties": False,
}


def _is_web_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlsplit(value.strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _normalise_results(payload: object, channel: dict) -> list[dict]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        return []
    hits = []
    for result in payload["results"]:
        if not isinstance(result, dict) or not _is_web_url(result.get("url")):
            continue
        hits.append(
            {
                "channel": channel.get("name"),
                "title": str(result.get("title") or "Web result"),
                "url": result["url"].strip(),
                "content": str(result.get("content") or "")[: settings.hit_content_chars],
            }
        )
    return hits


def responses_web_search(query: str, channel: dict) -> list[dict]:
    """Search with Responses' web tool and return source artifacts.

    This is only called after Tavily reports an HTTP/provider error.  A valid
    zero-result Tavily response remains a zero-result search rather than paying
    for a second provider.
    """
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is required: Responses web search is the active search provider"
        )
    if not _claim_budget():
        # Bounded autonomy: the run has spent its search allowance. Refusing further paid calls
        # is deliberate and is reported in the run summary, not hidden.
        return []

    tool: WebSearchToolParam = {"type": "web_search", "search_context_size": "medium"}
    if domain := channel.get("domain"):
        tool["filters"] = {"allowed_domains": [domain]}
    prompt = "\n".join(
        [
            "Search the web for the query below. Return only real source pages relevant to it.",
            "For each result, provide its page title, its exact public http(s) URL, and a concise",
            "source-grounded excerpt naming people, teams, projects, or achievements when present.",
            "Do not invent URLs or people. Return no more than 8 results.",
            f"Query: {query}",
        ]
    )
    try:
        response = OpenAI(api_key=settings.openai_api_key).responses.create(
            model=settings.model_fast,
            input=prompt,
            tools=[tool],
            max_output_tokens=1800,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "sourcing_web_results",
                    "strict": True,
                    "schema": _RESULT_SCHEMA,
                }
            },
        )
        return _normalise_results(json.loads(response.output_text), channel)
    except (APIError, httpx.HTTPError, json.JSONDecodeError) as exc:
        # Provider-side failure: one flaky query must not sink a parallel discovery run.
        # TypeError/ValueError are deliberately NOT caught — a malformed request or schema is
        # our own contract bug and must surface rather than degrade to permanent zero results.
        _record_failure(str(exc))
        return []
