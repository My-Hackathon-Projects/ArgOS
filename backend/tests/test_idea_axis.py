"""Deterministic guarantees of the idea-vs-market axis: anti-fabrication anchor + cold-start rule.

The LLM call itself is exercised end-to-end against real data (see progress.txt); here we lock
the pure post-processing that must hold regardless of what the model returns.
"""

from app.screening.idea_axis import IdeaAxisLLM, finalize_idea


def _out(**kw) -> IdeaAxisLLM:
    base = dict(
        verdict="pivot_needed", score=55.0, confidence=0.9, rationale="r", evidence_claim_ids=[]
    )
    base.update(kw)
    return IdeaAxisLLM(**base)


def _verdict(v: str) -> str:
    return finalize_idea(_out(verdict=v), valid_ids=set(), n_founder_claims=10).verdict


def test_verdict_maps_to_axis_enum():
    assert _verdict("survives_as_is") == "bull"
    assert _verdict("pivot_needed") == "neutral"
    assert _verdict("fails") == "bear"


def test_anchor_drops_fabricated_citations():
    out = _out(evidence_claim_ids=["real-1", "HALLUCINATED", "real-2"])
    r = finalize_idea(out, valid_ids={"real-1", "real-2"}, n_founder_claims=10)
    assert r.evidence["claim_ids"] == ["real-1", "real-2"]
    assert any("dropped 1" in g for g in r.gaps)


def test_cold_start_caps_confidence_but_not_verdict():
    out = _out(verdict="fails", confidence=0.95)
    r = finalize_idea(out, valid_ids=set(), n_founder_claims=2)  # < COLD_START_MIN_TEAM_CLAIMS
    assert r.confidence <= 0.5  # capped
    assert r.verdict == "bear"  # verdict itself untouched
    assert any("thin team evidence" in g for g in r.gaps)


def test_enough_team_evidence_keeps_confidence():
    r = finalize_idea(_out(confidence=0.9), valid_ids=set(), n_founder_claims=10)
    assert r.confidence == 0.9
