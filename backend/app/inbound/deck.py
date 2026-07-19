"""Inbound deck ingestion — pitch-deck PDF -> per-page signals.

Ported from BE/app/service/inboud_pipeline (pymupdf parsing); persistence adapted to the
backend signal table via the connector envelope. One signal per deck page, page number
preserved so downstream claims can cite "deck p.N". (source, external_id) unique on
("inbound", "deck:{opportunity_id}:p{N}") makes re-uploads idempotent.
"""

import uuid

from app.connectors.base import SignalEnvelope

# Founder-asserted material — low reliability prior; deck-only claims stay 'unverified'
# under the shared trust formula until externally corroborated.
DECK_SOURCE_RELIABILITY = 0.4


def parse_deck(
    pdf_bytes: bytes, company_name: str, opportunity_id: uuid.UUID
) -> list[SignalEnvelope]:
    """One SignalEnvelope per deck page. Raises on empty/unparseable/text-free PDFs."""
    import fitz  # pymupdf

    if not pdf_bytes:
        raise ValueError("deck PDF is empty")

    envelopes: list[SignalEnvelope] = []
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page_no, page in enumerate(doc, start=1):
            text = page.get_text().strip()
            envelopes.append(
                SignalEnvelope(
                    source="inbound",
                    signal_type="deck",
                    external_id=f"deck:{opportunity_id}:p{page_no}",
                    entity_hint=company_name,
                    title=f"{company_name} — deck p.{page_no}",
                    summary=text[:500] or None,
                    source_reliability=DECK_SOURCE_RELIABILITY,
                    raw={"page": page_no, "text": text, "opportunity_id": str(opportunity_id)},
                )
            )

    if not envelopes:
        raise ValueError("deck PDF has no pages")
    if all(not env.raw["text"] for env in envelopes):
        raise ValueError("deck PDF has no extractable text (image-only deck?)")
    return envelopes
