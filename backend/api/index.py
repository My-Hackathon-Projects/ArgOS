"""Vercel Python entrypoint — exposes the FastAPI app as an ASGI application.

Vercel routes every request here via vercel.json rewrites. Run with
CRON_ENABLED=false in production: serverless instances are ephemeral, so the
APScheduler loop must stay off (Vercel Cron can hit POST /discovery/run instead).
"""

from app.main import app

__all__ = ["app"]
