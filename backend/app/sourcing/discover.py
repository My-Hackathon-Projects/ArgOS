"""End-to-end discovery run against the real DB (no server needed).

Run: uv run python -m app.sourcing.discover
"""

import sys

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import Founder, JobRun, Signal
from app.sourcing.seed_data import sync_reference_data
from app.sourcing.service import run_discovery


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows console: allow → and accents
    db = SessionLocal()
    try:
        sync_reference_data(db)
        summary = run_discovery(db)
        print("\n=== discovery summary ===")
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
