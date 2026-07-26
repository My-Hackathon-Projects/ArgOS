"""A strong identity handle only identifies while exactly one person claims it.

`entity_resolution` states the assumption outright — "a shared public profile
(github/linkedin/twitter/orcid) is person-unique" — and STRONG_IDENTITY_KINDS merges on it.
Organisation accounts break it: the dev DB holds two different co-founders (Alex Rohregger,
Pasha Rizali) both carrying github:TheRobotStudio, their company's org account, recorded
silently with no resolution review.

The fix is not to delete the handle. It is real, it is on both public profiles, and deleting it
would destroy provenance and the conflict signal a human needs. Instead the *matcher* stops
counting it: once two known people claim a handle, it no longer distinguishes anyone, so it is
excluded from merge evidence. A handle only one person claims is unaffected, which is why the
existing conflict/review path keeps working.
"""

from app.entity_resolution import FounderCandidate, resolve_candidates


def _person(fid: str, name: str, **handles) -> FounderCandidate:
    return FounderCandidate(founder_id=fid, display_name=name, city="Munich", **handles)


def test_a_handle_two_people_claim_is_not_merge_evidence() -> None:
    """The live case: an org account held by two co-founders must not pull in a third person.

    The third name is deliberately close to an existing one — that is the combination the
    resolver would otherwise treat as proof of the same person.
    """
    existing = [
        _person("1", "Alex Rohregger", github="TheRobotStudio"),
        _person("2", "Pasha Rizali", github="TheRobotStudio"),
    ]
    incoming = FounderCandidate(display_name="Alex Rohregger", github="TheRobotStudio")

    result = resolve_candidates(incoming, existing)
    assert result.decision != "merge", (
        f"merged on an org handle two people already claim (matched {result.matched_id})"
    )
    assert "github" not in result.reasons


def test_a_handle_only_one_person_claims_still_merges() -> None:
    """The gate must not blunt the strong-identity tier in the normal case."""
    existing = [
        _person("1", "Alex Rohregger", github="arohregger"),
        _person("2", "Pasha Rizali", github="prizali"),
    ]
    incoming = FounderCandidate(display_name="Alex Rohregger", github="arohregger")

    result = resolve_candidates(incoming, existing)
    assert result.decision == "merge"
    assert result.matched_id == "1"
    assert "github" in result.reasons


def test_a_singly_claimed_handle_under_a_different_name_is_still_a_conflict() -> None:
    """The existing review path is untouched: one claimant means the handle still speaks."""
    existing = [_person("1", "Alex Rohregger", github="shared-handle")]
    incoming = FounderCandidate(display_name="Pasha Rizali", github="shared-handle")

    result = resolve_candidates(incoming, existing)
    assert result.decision == "review"
    assert "github" in result.conflicts


# ── name is the first-order gate ─────────────────────────────────────────────
# A shared identifier is only evidence about *which* person; it cannot establish that two
# obviously different names are one human. The strong-identity branch was the single merge path
# not gated on the name (artifact and context both require >= NAME_MATCH_MIN), and its bar sat at
# NAME_UNRELATED_MAX = 60. Two unrelated Chinese names score 61.5 on shared n-grams, so
# reconcile proposed collapsing three distinct researchers who shared an org account.


def test_obviously_different_names_never_merge_however_strong_the_identifier() -> None:
    """Live case: these scored 61.5 and cleared a threshold of 60."""
    for a, b in [
        ("Xinyang Tong", "Pengxiang Ding"),
        ("Wenxuan Song", "Pengxiang Ding"),
        ("Alex Rohregger", "Pasha Rizali"),
    ]:
        existing = [_person("1", b, github="shared-handle")]
        incoming = FounderCandidate(display_name=a, github="shared-handle")
        result = resolve_candidates(incoming, existing)
        assert result.decision != "merge", f"{a} merged into {b}"


def test_spelling_variants_of_one_name_still_merge_on_a_personal_handle() -> None:
    """The other half of the rule: a real variant plus a personal handle must still merge."""
    for a, b in [
        ("Ada Lovelace", "Ada King Lovelace"),
        ("Dr. Ada Lovelace", "Ada Lovelace"),
        ("Jose Garcia", "José García"),
    ]:
        existing = [_person("1", b, github="ada-personal")]
        incoming = FounderCandidate(display_name=a, github="ada-personal")
        result = resolve_candidates(incoming, existing)
        assert result.decision == "merge", f"{a} failed to merge with {b}"
        assert result.matched_id == "1"
