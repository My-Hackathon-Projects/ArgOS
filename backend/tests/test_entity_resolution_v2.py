"""Red/green fixtures for the next entity-resolution contract.

The first fixtures are copied from duplicate and collision clusters observed in the local
development database on 2026-07-24. These tests describe target behavior before the resolver
implementation is refactored.
"""

from app.entity_resolution import FounderCandidate, resolve_candidates


def _candidate(name: str, **kwargs) -> FounderCandidate:
    return FounderCandidate(display_name=name, **kwargs)


def test_rebecca_middle_initial_is_same_person_with_shared_linkedin() -> None:
    result = resolve_candidates(
        _candidate(
            "Rebecca C. Reisch",
            city="Stuttgart/Tübingen",
            current_company="Cyber Valley",
            linkedin="https://de.linkedin.com/in/rebeccareisch?trk=org-employees",
        ),
        [
            _candidate(
                "Rebecca Reisch",
                city="Stuttgart/Tübingen",
                current_company="Cyber Valley",
                linkedin="https://de.linkedin.com/in/rebeccareisch",
            )
        ],
    )
    assert result.decision == "merge"
    assert result.confidence >= 0.95
    assert "linkedin" in result.reasons


def test_shared_github_account_merges_compatible_names() -> None:
    result = resolve_candidates(
        _candidate("Dr. Ada Lovelace", github="ada-lovelace"),
        [_candidate("Ada Lovelace", github="Ada-Lovelace/")],
    )
    assert result.decision == "merge"
    assert result.confidence >= 0.95
    assert "github" in result.reasons


def test_stefan_honorific_with_context_but_no_unique_identity_needs_review() -> None:
    result = resolve_candidates(
        _candidate("Prof. Stefan Feuerriegel", city="Munich", current_company="LMU Munich"),
        [_candidate("Stefan Feuerriegel", city="Munich", current_company="LMU Munich")],
    )
    assert result.decision == "review"
    assert result.confidence >= 0.85
    assert "name" in result.reasons


def test_doctor_honorific_is_removed_before_matching() -> None:
    result = resolve_candidates(
        _candidate("Dr. Ada Lovelace", linkedin="linkedin.com/in/ada-lovelace"),
        [_candidate("Ada Lovelace", linkedin="linkedin.com/in/ada-lovelace")],
    )
    assert result.decision == "merge"
    assert result.confidence >= 0.9
    assert "name" in result.reasons


def test_full_middle_name_omission_with_context_but_no_unique_identity_needs_review() -> None:
    result = resolve_candidates(
        _candidate(
            "Rebecca Claire Reisch",
            city="Tübingen",
            current_company="Cyber Valley",
        ),
        [_candidate("Rebecca Reisch", city="Tübingen", current_company="Cyber Valley")],
    )
    assert result.decision == "review"
    assert result.confidence >= 0.85
    assert "name" in result.reasons


def test_distinct_organizations_do_not_collapse_to_a_person_name_shape() -> None:
    result = resolve_candidates(
        _candidate("Ada Lovelace", city="London", current_company="Alpha Research Labs"),
        [_candidate("Ada Lovelace", city="London", current_company="Alpha Robotics Labs")],
    )
    assert result.decision == "review"
    assert "company" not in result.reasons


def test_shared_github_handle_is_conflict_when_names_disagree() -> None:
    result = resolve_candidates(
        _candidate(
            "Pasha Rizali",
            city="Munich",
            current_company="Munich Hacks Robotics",
            github="TheRobotStudio",
        ),
        [
            _candidate(
                "Alex Rohregger",
                city="Munich",
                current_company="Munich Hacks Robotics",
                github="TheRobotStudio",
            )
        ],
    )
    assert result.decision == "review"
    assert "github" in result.conflicts


def test_same_name_and_city_without_identity_is_not_automatic_merge() -> None:
    result = resolve_candidates(
        _candidate("John Smith", city="Berlin"),
        [_candidate("John Smith", city="Berlin")],
    )
    assert result.decision == "review"
