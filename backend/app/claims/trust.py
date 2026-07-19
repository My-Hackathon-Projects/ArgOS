"""Deterministic Trust Score — noisy-OR over evidence. No LLM, no recency (Q4 locked).

trust = (1 - Π(1-w_support)) * Π(1-w_refute)
  - independent corroboration lifts trust and saturates toward 1,
  - a refutation pulls it down multiplicatively (authoritative contradiction -> ~0).
Fully decomposable into trust_components — the "show the receipts" panel.
"""

from math import prod

VERIFIED_THRESHOLD = 0.7
CONTRADICTION_WEIGHT = 0.4  # a refute this strong flags the claim 'contradicted'
EXTERNAL_VERIFIED_WEIGHT = (
    0.8  # a supporting source this authoritative counts as external verification
)


def evidence_weight(
    source_reliability: float | None,
    resolution_confidence: float | None,
    relevance: float | None,
) -> float:
    """Strength of one evidence edge. Recency is deliberately NOT here (it's a Founder Score term)."""
    sr = source_reliability if source_reliability is not None else 0.4
    rc = resolution_confidence if resolution_confidence is not None else 0.7
    rel = relevance if relevance is not None else 0.8
    return max(0.0, min(1.0, sr * rc * rel))


def _noisy_or(weights: list[float]) -> float:
    return 1.0 - prod(1.0 - w for w in weights) if weights else 0.0


def trust_score(support_weights: list[float], refute_weights: list[float]) -> float:
    support = _noisy_or(support_weights)
    refute = _noisy_or(refute_weights)
    return round(support * (1.0 - refute), 4)


def derive_status(trust: float, refute_weights: list[float]) -> str:
    if any(w >= CONTRADICTION_WEIGHT for w in refute_weights):
        return "contradicted"
    if trust >= VERIFIED_THRESHOLD:
        return "verified"
    return "unverified"


def trust_components(
    support_weights: list[float], refute_weights: list[float], sources: list[str]
) -> dict:
    return {
        "support": round(_noisy_or(support_weights), 4),
        "refute": round(_noisy_or(refute_weights), 4),
        "corroboration_n": len(support_weights),
        "refutation_n": len(refute_weights),
        "sources": sources,
        "external_verified": any(w >= EXTERNAL_VERIFIED_WEIGHT for w in support_weights),
    }
