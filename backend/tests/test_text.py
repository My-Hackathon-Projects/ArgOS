"""Tests for inline claim-id stripping (keeps raw UUIDs out of memo/axis prose)."""

from app.text import strip_inline_ids


def test_strips_uuid_list_mid_sentence() -> None:
    s = (
        "drawing on the LangGraph-style approach "
        "[ea7a5673-d4cd-42fa-8ca2-af2c4ab60d25, fc50c7f0-535d-4203-9504-b71828462cc0]; "
        "then bundle RAG."
    )
    out = strip_inline_ids(s)
    assert "[" not in out and "ea7a5673" not in out
    assert out == "drawing on the LangGraph-style approach; then bundle RAG."


def test_strips_single_and_truncated() -> None:
    assert strip_inline_ids("pricing power [2eca4094-1ff5-4ce4-9a33-93ebe2543b12].") == (
        "pricing power."
    )
    assert strip_inline_ids("the approach [fc50c7f0-535d-...].") == "the approach."


def test_strips_trailing_citation() -> None:
    assert strip_inline_ids("Author of 'Build AI' [02db9be9-e333-4b98-93f8-7a1c982afc83]") == (
        "Author of 'Build AI'"
    )


def test_preserves_legit_brackets() -> None:
    for s in [
        "Raised a round in [2023].",
        "A [Series A] round closed.",
        "Backed by [a16z] early.",
        "growth [10 cited]",
    ]:
        assert strip_inline_ids(s) == s, f"wrongly stripped: {s!r} -> {strip_inline_ids(s)!r}"


def test_clean_text_untouched_and_idempotent() -> None:
    assert strip_inline_ids("No citations here at all.") == "No citations here at all."
    once = strip_inline_ids("infra [ea7a5673-d4cd-42fa-8ca2-af2c4ab60d25] layer")
    assert once == "infra layer"
    assert strip_inline_ids(once) == once
