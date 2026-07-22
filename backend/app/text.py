"""Small text utilities shared across the LLM-prose surfaces."""

import re

# Inline claim-id citations the LLM sometimes drops into prose despite the structured
# evidence_claim_ids slots — e.g. "...LangGraph approach [ea7a5673-d4cd-42fa-..., fc50c7f0-...]".
# Match a bracket holding one+ hex/uuid tokens (>=6 hex, optional dashes, optional truncation
# ellipsis), comma-separated. The >=6-hex floor spares legit refs: [2023] / [Series A] / [10 cited].
_INLINE_CLAIM_CITE = re.compile(
    r"\s*\[\s*"
    r"[0-9a-fA-F]{6,}(?:-[0-9a-fA-F]+)*(?:-?\.\.\.)?"
    r"(?:\s*,\s*[0-9a-fA-F]{6,}(?:-[0-9a-fA-F]+)*(?:-?\.\.\.)?)*"
    r"\s*\]"
)


def strip_inline_ids(s: str) -> str:
    """Remove inline claim-id citation groups from LLM prose, leaving clean text.

    Citations belong in the structured evidence arrays, never inside a sentence. Idempotent;
    heals the whitespace/punctuation a mid-sentence removal leaves behind.
    """
    out = _INLINE_CLAIM_CITE.sub("", s)
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([.,;:)])", r"\1", out)
    return out.strip()
