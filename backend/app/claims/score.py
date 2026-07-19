"""Founder Score — saturating aggregate over the founder's claims (Q6 locked). Recency lives HERE.

contribution(c) = trust(c) * impact(c) * category_weight[cat] * recency(c)
founder_score   = 100 * (1 - e^(-Σ contribution / K))   (saturating: volume doesn't dominate)
components      = same shape per {tech, execution, pedigree, influence} + momentum cross-cut.
"""

from datetime import UTC, datetime
from math import exp

from app.claims.schemas import CATEGORY_WEIGHT, COMPONENT

RECENCY_HALF_LIFE_DAYS = 540.0  # ~18 months
SATURATION_K = 3.0  # tune so a strong founder lands mid-high, not saturated
MOMENTUM_WINDOW_DAYS = 180


def recency_factor(occurred_at: datetime | None, now: datetime) -> float:
    if occurred_at is None:
        return 0.6  # unknown date -> neutral-ish, not zero
    if occurred_at.tzinfo is None:
        occurred_at = occurred_at.replace(tzinfo=UTC)
    age_days = max(0.0, (now - occurred_at).total_seconds() / 86400.0)
    return 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)


def _saturate(x: float) -> float:
    return round(100.0 * (1.0 - exp(-x / SATURATION_K)), 1)


def founder_score(claims: list[dict], now: datetime | None = None) -> tuple[float, dict]:
    """claims: [{trust, impact, category, occurred_at}] -> (score 0..100, components dict)."""
    now = now or datetime.now(UTC)
    buckets = {"tech": 0.0, "execution": 0.0, "pedigree": 0.0, "influence": 0.0}
    total = 0.0
    recent = 0.0
    for c in claims:
        occ = c.get("occurred_at")
        rec = recency_factor(occ, now)
        contrib = (
            (c.get("trust") or 0.0)
            * (c.get("impact") or 0.0)
            * CATEGORY_WEIGHT.get(c["category"], 0.5)
            * rec
        )
        total += contrib
        buckets[COMPONENT.get(c["category"], "execution")] += contrib
        if occ is not None:
            if occ.tzinfo is None:
                occ = occ.replace(tzinfo=UTC)
            if (now - occ).days <= MOMENTUM_WINDOW_DAYS:
                recent += contrib
    components = {k: _saturate(v) for k, v in buckets.items()}
    components["momentum"] = round(recent / total, 3) if total else 0.0
    return _saturate(total), components
