"""APScheduler cron for sourcing jobs — ACTIVE by default (config-toggled).

Enabled via settings.cron_enabled (env CRON_ENABLED, default true) and wired into the app
lifespan in main.py — starting the API starts the cron. Modest default cadence, tunable via env:
discovery every DISCOVERY_INTERVAL_MIN (default 60), refresh every REFRESH_INTERVAL_MIN
(default 360). First fire happens one interval after boot (not instantly), so restarting the
app doesn't stampede API credits.

The claims job stays registered but PAUSED (next_run_time=None): the claims engine is under
active development; resume_job("claims") when its owner wants it live. It polls only founders
whose signals changed, so resuming it later is cheap.
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.claims.service import claims_job
from app.config import settings
from app.sourcing.jobs import discovery_job, refresh_job


def build_scheduler() -> BackgroundScheduler:
    """Register sourcing jobs ACTIVE (first run = one interval after start); claims PAUSED."""
    sched = BackgroundScheduler()
    sched.add_job(
        discovery_job, "interval", minutes=settings.discovery_interval_min, id="discovery"
    )
    sched.add_job(refresh_job, "interval", minutes=settings.refresh_interval_min, id="refresh")
    sched.add_job(claims_job, "interval", minutes=15, id="claims", next_run_time=None)
    return sched


def start_scheduler() -> BackgroundScheduler:
    """Build + start the cron. Call from the app lifespan; shutdown() on teardown."""
    sched = build_scheduler()
    sched.start()
    return sched
