"""Cron job callables for sourcing — discovery + refresh. Decoupled from the claims engine.

- discovery_job: thesis → graph → persist NEW founders + signals.
- refresh_job: re-check the N stalest KNOWN founders → append any NEW signals (enrichment path;
  resolves back to the existing founder, dedup-skips already-stored signals).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal, engine
from app.models import Founder, InvestmentThesis
from app.sourcing.graph import _profile_one, build_discovery_graph
from app.sourcing.persist import persist_delivery
from app.sourcing.responses_search import (
    reset_search_budget,
    search_budget_used,
    search_failures,
)
from app.sourcing.thesis import DEFAULT_THESIS

log = logging.getLogger(__name__)

_OUTBOUND_SOURCING_LOCK = 437_116


@contextmanager
def _outbound_sourcing_lock() -> Iterator[bool]:
    """Allow exactly one discovery or refresh run across all backend processes.

    On its OWN connection, and session-scoped rather than transaction-scoped. The lock has to
    outlive the multi-minute LLM run it guards, and `pg_try_advisory_xact_lock` can only do that
    by holding a transaction open for the whole run — leaving a connection `idle in transaction`
    for minutes at a time. Postgres cannot vacuum past the oldest open transaction, so every
    table in the database stops being cleaned while the sourcing agent thinks. A session lock
    survives the commit below, so the guard connection sits plainly idle instead.
    """
    connection = engine.connect()
    acquired = False
    try:
        acquired = bool(
            connection.execute(
                text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": _OUTBOUND_SOURCING_LOCK}
            ).scalar()
        )
        connection.commit()
        yield acquired
    finally:
        if acquired:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": _OUTBOUND_SOURCING_LOCK}
            )
            connection.commit()
        connection.close()


def _search_usage() -> dict:
    """Paid-search accounting for the run, so cost and degradation are both visible."""
    failures = search_failures()
    return {
        "web_searches": search_budget_used(),
        "web_search_budget": settings.responses_search_max_calls,
        "web_search_failures": len(failures),
    }


def _load_thesis(db: Session) -> dict:
    row = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    if row is None:
        return DEFAULT_THESIS.model_dump()
    return {
        "industries": row.industries or [],
        "geo": row.geo or [],
        "stage": row.stage or [],
        "keywords": row.keywords or [],
        "founder_preferences": row.founder_preferences or {},
    }


def discovery_job() -> dict:
    """DISCOVERY cron: find NEW founders matching the thesis."""
    with _outbound_sourcing_lock() as acquired:
        if not acquired:
            return {"skipped": "outbound sourcing already running"}
        db = SessionLocal()
        try:
            reset_search_budget()
            thesis = _load_thesis(db)
            # Nothing is written and no transaction is held while the agent runs.
            db.rollback()
            state = build_discovery_graph().invoke({"thesis": thesis, "trace": []})
            summary = persist_delivery(db, state.get("founders", []), commit=False)
            db.commit()
            log.info(
                "discovery: %s new, %s resolved, %s reviews",
                summary.get("new_founders"),
                summary.get("resolved_to_existing"),
                summary.get("needs_review"),
            )
            return summary | _search_usage()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()


def refresh_job(limit: int = 5) -> dict:
    """REFRESH cron: re-check the N stalest known founders → append any new signals."""
    with _outbound_sourcing_lock() as acquired:
        if not acquired:
            return {"skipped": "outbound sourcing already running"}
        db = SessionLocal()
        try:
            reset_search_budget()
            thesis = _load_thesis(db)
            founders = (
                db.execute(
                    select(Founder)
                    .order_by(Founder.last_checked_at.asc().nullsfirst())
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            candidates = []
            for f in founders:
                ident = f.identities[0] if f.identities else None
                candidates.append(
                    {
                        "display_name": f.display_name,
                        "first_name": f.first_name,
                        "last_name": f.last_name,
                        "city": f.city,
                        "occupation": f.occupation,
                        "current_company": f.current_company,
                        "github": ident.github if ident else None,
                        "twitter": ident.twitter if ident else None,
                        "linkedin": ident.linkedin if ident else None,
                        "website": ident.website if ident else None,
                        "orcid": ident.orcid if ident else None,
                    }
                )
            # Read done, transaction closed: the profiling calls below are the multi-minute part.
            db.rollback()
            deliveries = [_profile_one(cand, thesis) for cand in candidates]
            summary = persist_delivery(db, deliveries, source="refresh", commit=False)
            db.commit()
            log.info("refresh: %d founders re-checked", len(candidates))
            return summary | _search_usage()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
