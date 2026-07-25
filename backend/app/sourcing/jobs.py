"""Cron job callables for sourcing — discovery + refresh. Decoupled from the claims engine.

- discovery_job: thesis → graph → persist NEW founders + signals.
- refresh_job: re-check the N stalest KNOWN founders → append any NEW signals (enrichment path;
  resolves back to the existing founder, dedup-skips already-stored signals).
"""

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Founder, InvestmentThesis
from app.sourcing.graph import _profile_one, build_discovery_graph
from app.sourcing.persist import persist_delivery
from app.sourcing.responses_search import (
    reset_search_budget,
    search_budget_used,
    search_failures,
)
from app.sourcing.thesis import DEFAULT_THESIS

_OUTBOUND_SOURCING_LOCK = 437_116


def _search_usage() -> dict:
    """Paid-search accounting for the run, so cost and degradation are both visible."""
    failures = search_failures()
    return {
        "web_searches": search_budget_used(),
        "web_search_budget": settings.responses_search_max_calls,
        "web_search_failures": len(failures),
    }


def _acquire_outbound_sourcing_lock(db: Session) -> bool:
    """Allow exactly one discovery or refresh run across all backend processes."""
    return bool(
        db.scalar(
            text("SELECT pg_try_advisory_xact_lock(:lock_id)"), {"lock_id": _OUTBOUND_SOURCING_LOCK}
        )
    )


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
    db = SessionLocal()
    try:
        if not _acquire_outbound_sourcing_lock(db):
            db.rollback()
            return {"skipped": "outbound sourcing already running"}
        reset_search_budget()
        thesis = _load_thesis(db)
        state = build_discovery_graph().invoke({"thesis": thesis, "trace": []})
        summary = persist_delivery(db, state.get("founders", []), commit=False)
        db.commit()
        return summary | _search_usage()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def refresh_job(limit: int = 5) -> dict:
    """REFRESH cron: re-check the N stalest known founders → append any new signals."""
    db = SessionLocal()
    try:
        if not _acquire_outbound_sourcing_lock(db):
            db.rollback()
            return {"skipped": "outbound sourcing already running"}
        reset_search_budget()
        thesis = _load_thesis(db)
        founders = (
            db.execute(
                select(Founder).order_by(Founder.last_checked_at.asc().nullsfirst()).limit(limit)
            )
            .scalars()
            .all()
        )
        deliveries = []
        for f in founders:
            ident = f.identities[0] if f.identities else None
            cand = {
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
            deliveries.append(_profile_one(cand, thesis))
        summary = persist_delivery(db, deliveries, source="refresh", commit=False)
        db.commit()
        return summary | _search_usage()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
