"""Discovery service: load thesis from DB → run graph → persist. The endpoint + cron call this."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.claims.service import run_claims
from app.models import InvestmentThesis
from app.sourcing.graph import build_discovery_graph
from app.sourcing.persist import persist_delivery
from app.sourcing.thesis import DEFAULT_THESIS


def load_thesis(db: Session) -> dict:
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


def run_discovery(db: Session) -> dict:
    thesis = load_thesis(db)
    graph = build_discovery_graph()
    state = graph.invoke({"thesis": thesis, "trace": []})
    summary = persist_delivery(db, state.get("founders", []))
    # Tail-call the claims layer for the founders this run touched (pending set) so fresh
    # founders get a Founder Score in the same pass — not on the next cron tick.
    claims = run_claims(db)
    summary["stats"] = state.get("stats", {})
    summary["stats"]["claims_founders_processed"] = claims["founders_processed"]
    summary["trace"] = state.get("trace", [])
    return summary
