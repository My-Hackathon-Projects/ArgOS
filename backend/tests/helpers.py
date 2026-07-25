"""Shared test helpers."""

import uuid

# Digits mark a non-person name (cohort years), so test fixtures that build unique founder
# names must stay alphabetic or the personhood gate rejects them.
_DIGITS_TO_LETTERS = str.maketrans("0123456789", "ghijklmnop")


def unique_suffix() -> str:
    """A collision-free, letters-only suffix safe to append to a test founder name."""
    return uuid.uuid4().hex.translate(_DIGITS_TO_LETTERS)
