"""Deterministic axis trend: this run's score vs the previously persisted one.

Shared by the idea and market axes (the founder axis derives its trend from the richer
ScoreHistory series instead). Same deadband idea as founder_axis.TREND_DEADBAND: tiny
score wobbles must not flip the arrow.
"""

TREND_DEADBAND = 1.0


def trend_vs_prev(prev: float | None, new: float | None) -> str:
    if prev is None or new is None:
        return "stable"  # first measurement — no history to compare against
    if new - prev > TREND_DEADBAND:
        return "improving"
    if prev - new > TREND_DEADBAND:
        return "declining"
    return "stable"
