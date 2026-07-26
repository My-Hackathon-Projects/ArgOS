"""`signal.kind` — the explicit provenance discriminator.

Before this column, "is this a founder signal or a market signal?" was answerable only by a
`NOT EXISTS` against `founder_signal`: an implicit rule no schema enforced and no reader could
see. The market writer mints web artifacts that must never enter the founder-claim pipeline,
and the two writers were distinguishable only by side effect.

`kind` records which writer minted the artifact. The cross-table rule ("a market artifact has no
founder attribution") is NOT a CHECK constraint — Postgres CHECK cannot reference another table —
so it is enforced at the single writer and asserted here over the live bed.

Dual use is real and allowed: one URL can be evidence about a founder AND about a market, and
`(source, external_id)` is unique, so both uses share one row. That is a *promotion* — attributing
a market-minted artifact to a founder flips `kind` to 'founder' explicitly rather than silently
leaving a market row wired into the founder pipeline.
"""

import uuid

import pytest
from helpers import unique_suffix
from sqlalchemy import func, select, text

from app.db import SessionLocal
from app.market.persist import persist_market
from app.models import Founder, Opportunity, Signal, founder_signal
from app.sourcing.persist import persist_delivery


def _founder_payload(name: str, suffix: str) -> dict:
    url = f"https://example.test/profile/{suffix}"
    return {
        "display_name": name,
        "status": "candidate",
        "discovery_confidence": 0.5,
        "signals": [
            {
                "source": "web",
                "signal_type": "profile",
                "canonical_url": url,
                "content_hash": f"hash-{suffix}",
                "url": url,
                "title": "Founder profile",
                "summary": "A person who builds things.",
                "source_reliability": 0.7,
                "resolution_confidence": 0.9,
                "resolution_method": "exact_key",
                "sources_seen": ["web"],
            }
        ],
    }


def _market_analysis(founder_id: uuid.UUID | None, suffix: str) -> dict:
    url = f"https://example.test/market-report/{suffix}"
    return {
        "opportunity": {
            "founder_id": str(founder_id) if founder_id else None,
            "company_name": f"Testco {suffix}",
            "idea": "agent orchestration",
            "sector": "devtools",
            "geo": "EU",
        },
        "hits_by_goal": {
            "sizing": [{"url": url, "title": "Market report", "content": "TAM is large."}]
        },
        "sizing": {
            "figures": [
                {
                    "metric": "TAM",
                    "value": "$1B",
                    "unit": "USD",
                    "basis": "report",
                    "citation_indices": [0],
                    "confidence": 0.8,
                }
            ]
        },
        "synthesis": {
            "axis": {
                "score": 70,
                "verdict": "bull",
                "rationale": "large and growing",
                "confidence": 0.7,
            },
            "gaps": [],
        },
    }


def test_sourcing_writer_mints_founder_kind() -> None:
    """The founder path stamps kind='founder' on every artifact it creates."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        result = persist_delivery(db, [_founder_payload(f"Ada Kind {suffix}", suffix)])
        assert result["new_signals"] == 1
        sig = db.execute(
            select(Signal).where(Signal.canonical_url == f"https://example.test/profile/{suffix}")
        ).scalar_one()
        assert sig.kind == "founder"
    finally:
        db.close()


def test_market_writer_mints_market_kind() -> None:
    """The market path stamps kind='market' — these must stay out of the founder pipeline."""
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Grace Kind {suffix}", status="candidate")
        db.add(founder)
        db.flush()
        opp = Opportunity(founder_id=founder.id, idea="agent orchestration", status="diligence")
        db.add(opp)
        db.flush()

        persist_market(db, _market_analysis(founder.id, suffix), opportunity_id=opp.id)

        sig = db.execute(
            select(Signal).where(
                Signal.canonical_url == f"https://example.test/market-report/{suffix}"
            )
        ).scalar_one()
        assert sig.kind == "market"
        # and it carries no founder attribution
        n = db.execute(
            select(func.count())
            .select_from(founder_signal)
            .where(founder_signal.c.signal_id == sig.id)
        ).scalar_one()
        assert n == 0
    finally:
        db.close()


def test_kind_rejects_unknown_value() -> None:
    """The value domain is a real CHECK constraint, not a convention."""
    db = SessionLocal()
    try:
        db.add(
            Signal(
                source="web",
                signal_type="profile",
                external_id=f"bogus-{unique_suffix()}",
                kind="nonsense",
            )
        )
        with pytest.raises(Exception, match="ck_signal_kind"):
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_kind_is_not_null() -> None:
    """No artifact may exist without declared provenance."""
    db = SessionLocal()
    try:
        eid = f"nokind-{unique_suffix()}"
        with pytest.raises(Exception, match="kind"):
            db.execute(
                text(
                    "INSERT INTO signal (id, source, signal_type, external_id) "
                    "VALUES (gen_random_uuid(), 'web', 'profile', :eid)"
                ),
                {"eid": eid},
            )
            db.flush()
    finally:
        db.rollback()
        db.close()


def test_market_artifact_is_promoted_when_founder_attributed() -> None:
    """Dual use: attributing a market artifact to a founder promotes it, never leaves it 'market'.

    One URL is minted by the market writer, then the founder writer resolves the same URL. The
    row is shared (source, external_id is unique), so the invariant would break unless the
    promotion is explicit.
    """
    db = SessionLocal()
    try:
        suffix = unique_suffix()
        founder = Founder(display_name=f"Alan Promote {suffix}", status="candidate")
        db.add(founder)
        db.flush()
        opp = Opportunity(founder_id=founder.id, idea="agent orchestration", status="diligence")
        db.add(opp)
        db.flush()
        persist_market(db, _market_analysis(founder.id, suffix), opportunity_id=opp.id)

        shared_url = f"https://example.test/market-report/{suffix}"
        sig = db.execute(select(Signal).where(Signal.canonical_url == shared_url)).scalar_one()
        assert sig.kind == "market"

        payload = _founder_payload(f"Bella Promote {suffix}", suffix)
        payload["signals"][0]["canonical_url"] = shared_url
        payload["signals"][0]["url"] = shared_url
        payload["signals"][0]["content_hash"] = None
        persist_delivery(db, [payload])

        db.expire_all()
        sig = db.execute(select(Signal).where(Signal.canonical_url == shared_url)).scalar_one()
        n = db.execute(
            select(func.count())
            .select_from(founder_signal)
            .where(founder_signal.c.signal_id == sig.id)
        ).scalar_one()
        assert n == 1, "the founder path reused the shared artifact"
        assert sig.kind == "founder", "reuse for founder attribution must promote kind"
    finally:
        db.close()


@pytest.mark.dev_bed
def test_no_market_artifact_carries_founder_attribution(dev_db) -> None:
    """The cross-table invariant, asserted over live data (no CHECK can express it)."""
    violations = dev_db.execute(
        text(
            "SELECT s.id, s.signal_type, s.canonical_url FROM signal s "
            "JOIN founder_signal fs ON fs.signal_id = s.id "
            "WHERE s.kind = 'market'"
        )
    ).all()
    assert not violations, f"market artifacts wired into the founder pipeline: {violations}"


@pytest.mark.dev_bed
def test_every_live_signal_has_kind(dev_db) -> None:
    n = dev_db.execute(text("SELECT count(*) FROM signal WHERE kind IS NULL")).scalar_one()
    assert n == 0
