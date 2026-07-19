"""LLM extraction + adjudication for claim generation. Structured output, no DB.

Cold build: one smart-model pass over ALL a founder's signals -> deduplicated claims.
Warm update: fast-model adjudication of a candidate against existing same-category claims.
"""

from langchain_openai import ChatOpenAI

from app.claims.schemas import CATEGORIES, ClaimExtraction, MatchDecision
from app.config import settings


def _llm(schema, smart: bool):
    model = settings.model_smart if smart else settings.model_fast
    # function_calling (not strict json_schema) so the flexible `attributes` object is allowed.
    return ChatOpenAI(model=model, api_key=settings.openai_api_key).with_structured_output(
        schema, method="function_calling"
    )


def _signals_block(signals: list[dict]) -> str:
    return "\n\n".join(
        f"[{i}] source={s['source']} type={s['signal_type']} date={s.get('occurred_at')}\n"
        f"    title: {s.get('title') or ''}\n"
        f"    summary: {s.get('summary') or ''}\n"
        f"    url: {s.get('canonical_url')}"
        for i, s in enumerate(signals)
    )


def extract_claims(founder: dict, signals: list[dict], smart: bool = True) -> ClaimExtraction:
    """Synthesize a deduplicated claim set from the provided (indexed) signals."""
    prompt = f"""You are a VC analyst extracting evidence-backed CLAIMS about a founder from their public signals.

## Founder
name: {founder.get("display_name")}
occupation: {founder.get("occupation")}
current_company: {founder.get("current_company")}

## Signals (indexed)
{_signals_block(signals)}

## Task
Extract every distinct, evidence-backed CLAIM about THIS PERSON. A claim is ONE assertion of fact
(a role, a degree, a paper, a launch, an award, a skill) — NOT a summary of everything.

## Rules
1. Category: use exactly one of: {", ".join(CATEGORIES)}.
2. ONE claim per distinct role / degree / artifact. NEVER merge "worked at 3 places" into one claim —
   emit three separate employment claims (ex-Amazon, ex-BCG, ex-McKinsey are three claims).
3. Corroboration: if several signals evidence the SAME fact, emit ONE claim listing all their indices
   in supporting_signals. Three references to one paper become one strong claim.
4. impact 0..1 = how significant THIS specific fact is (NeurIPS first-author ~0.9, 10k-star repo ~0.85,
   a generic CS degree ~0.4, a meetup talk ~0.2).
5. Only assert what the signals support. Every claim MUST cite >=1 supporting signal index. Never invent.
6. refuting_signals: only if a signal genuinely CONTRADICTS the claim (usually empty).
7. dedup_key: a stable key if obvious (arxiv id, github owner/repo, canonical url); else null.
8. attributes: structured bits (company/title/start/end, venue/year, metric/value).

Extract the claims now."""
    return _llm(ClaimExtraction, smart=smart).invoke(prompt)


def adjudicate(candidate: dict, existing: list[dict], smart: bool = False) -> MatchDecision:
    """Does the candidate assert the same fact as one of the founder's existing same-category claims?"""
    listing = "\n".join(f"[{i}] {e['statement']}" for i, e in enumerate(existing))
    prompt = f"""Decide whether a NEW candidate claim about a founder is the SAME fact as one they already have.

## Candidate claim (category={candidate["category"]})
{candidate["statement"]}

## Existing claims in this category
{listing}

## Task
If the candidate asserts the SAME underlying fact as one existing claim, return action='attach' with its
existing_index, and stance='supports' (or 'refutes' if it CONTRADICTS that claim). If it is a genuinely
NEW fact, return action='mint'. When unsure, prefer 'mint' — a wrong merge is worse than a duplicate."""
    return _llm(MatchDecision, smart=smart).invoke(prompt)
