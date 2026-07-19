"""checkpointer.py — the one shared LangGraph checkpointer factory.

All graphs (inbound, validation, and later outbound) checkpoint into the SAME
saver so ``thread_id`` stays the single correlation key across API routes,
checkpoints, domain rows, and LangSmith traces (§2 / §7 of the service README).

Set ``SERVICE_CHECKPOINTER=postgres`` to use the FastAPI app's Postgres DB;
anything else (default) uses an in-memory saver so the pipelines run in tests
and local dev without a database.
"""

from __future__ import annotations

import os


def _postgres_dsn() -> str:
    """Reuse the FastAPI app's Postgres DSN, stripped to a plain psycopg DSN."""
    from app.core.config import settings

    return str(settings.SQLALCHEMY_DATABASE_URI).replace(
        "postgresql+psycopg", "postgresql"
    )


def get_checkpointer():
    """
    Return the process-wide saver: PostgresSaver when
    ``SERVICE_CHECKPOINTER=postgres``, InMemorySaver otherwise. Checkpoints
    after every node give us crash-resume, the live status endpoint,
    time-to-decision metrics, and the replayable reasoning trace for free.
    """
    if os.getenv("SERVICE_CHECKPOINTER", "memory").lower() == "postgres":
        from langgraph.checkpoint.postgres import PostgresSaver

        # Opened for the process lifetime (module-level singleton graphs).
        # .setup() creates the checkpoints* tables (separate from Alembic).
        saver = PostgresSaver.from_conn_string(_postgres_dsn()).__enter__()
        saver.setup()
        return saver

    from langgraph.checkpoint.memory import InMemorySaver

    return InMemorySaver()
