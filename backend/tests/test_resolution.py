"""Deterministic tests for founder name-normalization (the resolution matcher).

Resolution merges two founder records when `_norm_name(a) == _norm_name(b)` (after the
strong-id tier). These cases pin the behavior so future changes can't silently regress it:

- SAME_PERSON: real duplicates we observed in the live DB (honorific prefixes, middle
  initials) plus accent/case/whitespace variants — MUST collapse to one key.
- DIFFERENT_PEOPLE: real false-positive pairs from the DB (same surname, different first
  name) — MUST stay distinct (no over-merging).
"""

import pytest

from app.sourcing.persist import _norm_name

# Variants of the SAME person — must produce the same normalized key.
SAME_PERSON = [
    # honorific prefixes (real dup: LMU Munich)
    ("Prof. Stefan Feuerriegel", "Stefan Feuerriegel"),
    ("Prof. Dr. Stefan Feuerriegel", "Stefan Feuerriegel"),
    ("Dr. Stefan Feuerriegel", "Stefan Feuerriegel"),
    # middle initial (real dup: Cyber Valley)
    ("Rebecca C. Reisch", "Rebecca Reisch"),
    ("Rebecca C Reisch", "Rebecca Reisch"),
    ("Noah A. Smith", "Noah Smith"),
    # accents / case / whitespace (already handled — guard against regression)
    ("Jürgen Schmidhuber", "Jurgen Schmidhuber"),
    ("  Sami   Haddadin ", "Sami Haddadin"),
    ("YEJIN CHOI", "Yejin Choi"),
    # honorific + initial together
    ("Prof. Rebecca C. Reisch", "Rebecca Reisch"),
]

# DIFFERENT people who share a surname (and city/company) — must NOT collapse.
DIFFERENT_PEOPLE = [
    ("Jingcheng Wu", "Fan Wu"),
    ("Jingpei Wu", "Fan Wu"),
    ("Zy Zhang", "Yu Zhang"),
    ("Liding Zhang", "Yu Zhang"),
    ("Qian Huang", "Yuhong Huang"),
    ("Stefan Feuerriegel", "Stefan Feuchtinger"),
]


@pytest.mark.parametrize("a,b", SAME_PERSON)
def test_same_person_collapses(a: str, b: str) -> None:
    assert _norm_name(a) == _norm_name(b), (
        f"{a!r} and {b!r} are the same person but normalized to "
        f"{_norm_name(a)!r} != {_norm_name(b)!r}"
    )


@pytest.mark.parametrize("a,b", DIFFERENT_PEOPLE)
def test_different_people_stay_distinct(a: str, b: str) -> None:
    assert _norm_name(a) != _norm_name(b), (
        f"{a!r} and {b!r} are different people but both normalized to {_norm_name(a)!r}"
    )


def test_empty_and_titles_only() -> None:
    assert _norm_name(None) == ""
    assert _norm_name("   ") == ""
    # a string of only honorifics resolves to empty (no name to match on)
    assert _norm_name("Prof. Dr.") == ""
