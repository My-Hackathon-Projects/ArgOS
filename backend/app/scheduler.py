"""APScheduler cron for sourcing jobs — DISABLED by default.

Jobs are defined here but the scheduler is NOT started automatically (no hook wired into
main.py). Both jobs are also registered PAUSED (next_run_time=None), so even a started
scheduler fires nothing until explicitly resumed. This keeps them "ready in theory" without
running during the hackathon build.

Cadence: discovery hourly, refresh daily (config-tunable later).

── To enable (currently OFF) ── add to app/main.py `lifespan`:
    from app.scheduler import start_scheduler
    scheduler = start_scheduler()        # registered but PAUSED
    scheduler.resume_job("discovery")    # ...resume when you want it live
    scheduler.resume_job("refresh")
    # and scheduler.shutdown() on teardown
"""

from apscheduler.schedulers.background import BackgroundScheduler

from app.sourcing.jobs import discovery_job, refresh_job


def build_scheduler() -> BackgroundScheduler:
    """Register both jobs PAUSED (next_run_time=None → won't fire until resume_job(id))."""
    sched = BackgroundScheduler()
    sched.add_job(discovery_job, "interval", hours=1, id="discovery", next_run_time=None)
    sched.add_job(refresh_job, "interval", days=1, id="refresh", next_run_time=None)
    return sched


def start_scheduler() -> BackgroundScheduler:
    """Build + start the scheduler (jobs still paused until resume_job is called)."""
    sched = build_scheduler()
    sched.start()
    return sched
