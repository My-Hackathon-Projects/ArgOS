"""End-to-end DISCOVERY run against the real DB (signal generation only — claims decoupled).

Owns just the sourcing half: sync reference data → load thesis → run graph → persist signals.
Deliberately does NOT call the claims engine (actively being built elsewhere), so signal
generation + enrichment can be tested in isolation.

Run: uv run python -m app.sourcing.discover
"""

import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Founder, InvestmentThesis, JobRun, Signal
from app.sourcing.graph import build_discovery_graph
from app.sourcing.persist import persist_delivery
from app.sourcing.seed_data import sync_reference_data
from app.sourcing.thesis import DEFAULT_THESIS


def _load_thesis(db) -> dict:
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


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    db = SessionLocal()
    try:
        sync_reference_data(db)
        thesis = _load_thesis(db)
        graph = build_discovery_graph()
        state = graph.invoke({"thesis": thesis, "trace": []})
        summary = persist_delivery(db, state.get("founders", []))
        summary["stats"] = state.get("stats", {})

        print("\n=== discovery summary (signals only; claims decoupled) ===")
        print(summary)

        n_founders = db.execute(select(func.count()).select_from(Founder)).scalar_one()
        n_signals = db.execute(select(func.count()).select_from(Signal)).scalar_one()
        n_jobs = db.execute(select(func.count()).select_from(JobRun)).scalar_one()
        print(f"\nDB totals: founders={n_founders} signals={n_signals} job_runs={n_jobs}")
        for f in db.execute(
            select(Founder).order_by(Founder.first_discovered_at.desc().nullslast())
        ).scalars():
            sc = db.execute(
                select(func.count()).select_from(Signal).where(Signal.founder_id == f.id)
            ).scalar_one()
            print(
                f"  - {f.display_name} [{f.status}] conf={f.discovery_confidence} "
                f"company={f.current_company} signals={sc}"
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()
