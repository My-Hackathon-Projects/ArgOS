"""APScheduler cron for the agent loop — ACTIVE by default (config-toggled).

Enabled via settings.cron_enabled (env CRON_ENABLED, default true) and wired into the app
lifespan in main.py — starting the API starts the cron. Modest default cadence, tunable via env:
discovery every DISCOVERY_INTERVAL_MIN (default 60), refresh every REFRESH_INTERVAL_MIN
(default 360), claims every CLAIMS_INTERVAL_MIN (default 15). Sourcing jobs first fire one
interval after boot (no credit stampede on restarts); claims first fires shortly after boot so
freshly discovered founders get scored without waiting a full interval.

The claims job is cheap when idle: it polls only founders whose signals changed since their
last claims pass — untouched founders cost one indexed query, nothing more.
"""

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from app.claims.service import claims_job
from app.config import settings
from app.sourcing.jobs import discovery_job, refresh_job


def build_scheduler() -> BackgroundScheduler:
    """Register all loop jobs ACTIVE: discovery + refresh + claims (signals → scores)."""
    sched = BackgroundScheduler()
    sched.add_job(
        discovery_job, "interval", minutes=settings.discovery_interval_min, id="discovery"
    )
    sched.add_job(refresh_job, "interval", minutes=settings.refresh_interval_min, id="refresh")
    sched.add_job(
        claims_job,
        "interval",
        minutes=settings.claims_interval_min,
        id="claims",
        # First pass ~2min after boot: score whatever discovery already ingested.
        next_run_time=datetime.now(UTC) + timedelta(minutes=2),
    )
    return sched


def start_scheduler() -> BackgroundScheduler:
    """Build + start the cron. Call from the app lifespan; shutdown() on teardown."""
    sched = build_scheduler()
    sched.start()
    return sched
