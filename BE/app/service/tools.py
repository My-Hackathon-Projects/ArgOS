# Stub pass: external/repo signatures are final, bodies are TODO — their args
# are intentionally unused for now.
# ruff: noqa: ARG001
"""tools.py — external sources + Memory access.

Two families, deliberately kept apart:

1. **External tools** — HTTP clients for GitHub / HN / arXiv, PDF parsing, LLM
   client factories. Trust boundary rule: anything returned from outside enters
   the system **only as a ``Signal``** (raw_payload preserved). External data is
   never trusted directly into a score — it must become evidence first, cited
   later by ``evidence_ids``.
2. **Repository** — thin, dumb SQL access to Postgres (the Memory layer). Nodes
   never write SQL themselves. Domain rows and LangGraph checkpoints share the
   same database, joined by ``opportunity_id``.

STATUS: skeleton pass. The LLM factories are real; every other function is a
stub returning seed / no-op data behind its final signature, so real HTTP and
SQL implementations drop in later without touching nodes.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

from langchain.chat_models import init_chat_model

from app.service.models import (
    Claim,
    Company,
    Decision,
    Founder,
    Memo,
    Signal,
    Thesis,
    TrustScore,
)

# ============================ 1. EXTERNAL TOOLS ============================


def get_fast_llm():
    """
    Return the cheap/fast chat model (e.g. Haiku-class), used by pre_screen
    and claim extraction. Centralized here so model choice/config is one
    line to change. Always used with .with_structured_output(<Model>) —
    free-text responses are banned pipeline-wide.
    """
    return init_chat_model("openai:gpt-4o-mini", temperature=0)


def get_strong_llm():
    """
    Return the strong reasoning model (e.g. Sonnet/Opus-class), used by the
    three axis agents, the validator, and the memo writer.
    """
    return init_chat_model("openai:gpt-4o", temperature=0)


def parse_deck_pdf(pdf_bytes: bytes) -> list[Signal]:
    """
    Turn an uploaded pitch deck into Signals: extract per-page text (and
    page numbers! source_pointer="deck p.N" depends on it) with pymupdf.
    Returns one Signal per page/section with source_type="deck" and the
    raw text preserved in raw_payload. No interpretation here — claim
    extraction is a node, not a tool.
    """
    # TODO: fitz.open(stream=pdf_bytes) -> one Signal per page.
    return []


def scan_github(query_or_topic: str, limit: int) -> list[Signal]:
    """
    Hit the GitHub REST API (trending/search: repos + committer profiles)
    and return raw Signals with source_type="github" and entity_hints
    (usernames, display names) for entity resolution. Also reused by the
    validator to fact-check claims like "2K stars".
    """
    # TODO: httpx GET api.github.com/search/repositories.
    return []


def scan_hackernews(query: str, limit: int) -> list[Signal]:
    """
    Query the HN Algolia API for Show HN / launch posts. Returns Signals
    with source_type="hn". Used by outbound sourcing and by the validator
    to verify "we launched on HN" claims.
    """
    # TODO: httpx GET hn.algolia.com/api/v1/search.
    return []


def scan_arxiv(query: str, limit: int) -> list[Signal]:
    """
    Query the arXiv API for recent papers matching thesis sectors. Returns
    Signals with source_type="arxiv", author names as entity_hints —
    the 'paper worth a phone call' sourcing channel.
    """
    # TODO: httpx GET export.arxiv.org/api/query.
    return []


def load_seed_signals() -> list[Signal]:
    """
    Load the synthetic dataset (15-20 fake founders, including 2-3 with
    SEEDED CONTRADICTIONS and 2 cold-start profiles). Everyone develops
    against this from hour 1; the demo's "validator catches the lying
    deck" moment comes from here.
    """
    now = datetime.now(UTC).isoformat()
    # Minimal seed: one deck signal with a checkable claim + one github signal
    # that will contradict it (the "lying deck" demo moment).
    return [
        Signal(
            id="sig-seed-deck-1",
            source_type="deck",
            source_url=None,
            raw_payload={
                "page": 4,
                "text": "Traction: 12K GitHub stars, $50K MRR. Team ex-Google.",
            },
            entity_hints=["jane-doe", "Jane Doe"],
            fetched_at=now,
        ),
        Signal(
            id="sig-seed-github-1",
            source_type="github",
            source_url="https://github.com/jane-doe/project",
            raw_payload={"stars": 180, "owner": "jane-doe"},
            entity_hints=["jane-doe"],
            fetched_at=now,
        ),
    ]


def verify_claim_external(claim: Claim, signals: list[Signal]) -> dict:
    """
    The validator's fact-checking tool. Given a Claim, decide which
    external check applies (GitHub stars -> scan_github, launch ->
    scan_hackernews, ...), run it, and return
    {supporting_signal_ids, conflicting_signal_ids, notes}.
    Fetched evidence is ALSO saved as new Signals (nothing discarded).
    """
    # TODO: route by claim.category, call the right scan_*, diff against claim.
    return {
        "supporting_signal_ids": [],
        "conflicting_signal_ids": [],
        "notes": "",
    }


def draft_outreach(founder: Founder, signals: list[Signal], thesis: Thesis) -> str:
    """
    Generate the cold-outreach message for a strong outbound candidate.
    Goal per brief: trigger a real application ("cold outreach, not cold
    investment"). Returned draft is stored and shown in the Outbound Queue
    screen — we do NOT actually send email in the hackathon.
    """
    # TODO: get_strong_llm() prompt over founder + signals + thesis.
    return ""


# ====================== 2. REPOSITORY (Memory access) ======================
# Seed-data / no-op stubs this pass. Signatures are final so the real SQL
# implementation (shared engine from app.core.db) drops in behind them.


def save_signals(signals: list[Signal]) -> None:
    """
    Append-only INSERT into the signals table. Idempotent on
    (source_url, fetched_at-ish) so re-scans don't duplicate (NFR-4).
    Never UPDATE, never DELETE.
    """
    # TODO: real INSERT ... ON CONFLICT DO NOTHING.
    return None


def upsert_entities(founder: Founder, company: Company) -> tuple[Founder, Company]:
    """
    Write resolved entities. Upsert semantics: if entity resolution matched
    an existing founder (same GitHub handle seen months ago), merge into
    the canonical row and RETURN it — this is what makes the Founder Score
    persist across applications.
    """
    # TODO: real upsert; for now echo back.
    return founder, company


def find_matching_founder(entity_hints: list[str]) -> Founder | None:
    """
    Entity resolution lookup: exact handle match first, then fuzzy
    name match (+ optional pgvector similarity on profile text).
    Returns the canonical Founder or None (-> new entity).
    """
    # TODO: exact-handle SQL, then fuzzy, then pgvector.
    return None


def get_founder_history(founder_id: str) -> dict:
    """
    Pull everything Memory knows about a person: past signals, past
    opportunities/decisions, and the full founder score_history. This is
    the axis agents' evidence base, and the Founder axis input.
    """
    # TODO: join signals + opportunities + decisions + score_history.
    return {"signals": [], "opportunities": [], "score_history": []}


def save_claims(claims: list[Claim]) -> None:
    """Insert extracted claims; later updated in place with TrustScores."""
    # TODO: real INSERT.
    return None


def update_claim_trust(claim_id: str, trust: TrustScore) -> None:
    """Write the validator's TrustScore + contradictions onto a claim row."""
    # TODO: real UPDATE claims SET trust = ... WHERE id = claim_id.
    return None


def log_rejection(opportunity_id: str, reason: str) -> None:
    """
    Persist pre-screen rejections with reasons. Rejected != deleted —
    the signal history stays in Memory and still feeds the Founder Score.
    """
    # TODO: real INSERT into rejections.
    return None


def save_memo(memo: Memo) -> None:
    """Insert the finished memo (sections, gaps, recommendation, trace_ref)."""
    # TODO: real INSERT.
    return None


def finalize_opportunity(
    opportunity_id: str, decision: Decision, axis_scores: dict
) -> None:
    """
    The writeback node's single transaction: persist the human decision,
    persist the three axis scores, recompute + append the new Founder
    Score point, stamp final stage_timestamps. Invariant: domain tables
    contain only human-gated conclusions; everything provisional lives in
    checkpoints.
    """
    # TODO: one transaction — decision + axis scores + founder score point.
    return None


def nl_query_to_cards(text: str) -> list[dict]:
    """
    Multi-attribute reasoning (FR-8): LLM parses the compound sentence into
    structured filters -> SQL WHERE + pgvector similarity -> ranked
    opportunity rows, one pass. Lives here (not in the graph) because it's
    a synchronous read path called by POST /query.
    """
    # TODO: get_fast_llm().with_structured_output(<Filter>) -> SQL -> rows.
    return []
