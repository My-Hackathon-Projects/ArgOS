"""Cron job callables for sourcing — discovery + refresh. Decoupled from the claims engine.

- discovery_job: thesis → graph → persist NEW founders + signals.
- refresh_job: re-check the N stalest KNOWN founders → append any NEW signals (enrichment path;
  resolves back to the existing founder, dedup-skips already-stored signals).
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import SessionLocal
from app.models import Founder, InvestmentThesis
from app.sourcing.graph import _profile_one, build_discovery_graph
from app.sourcing.persist import persist_delivery
from app.sourcing.thesis import DEFAULT_THESIS


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
        thesis = _load_thesis(db)
        state = build_discovery_graph().invoke({"thesis": thesis, "trace": []})
        return persist_delivery(db, state.get("founders", []))
    finally:
        db.close()


def refresh_job(limit: int = 5) -> dict:
    """REFRESH cron: re-check the N stalest known founders → append any new signals."""
    db = SessionLocal()
    try:
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
        return persist_delivery(db, deliveries)
    finally:
        db.close()
