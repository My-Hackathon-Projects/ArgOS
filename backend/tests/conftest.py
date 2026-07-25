"""Test isolation.

Every test runs against a dedicated database inside a transaction that is always rolled back.

This exists because the suite previously ran against the shared dev database through the
module-level ``app.db.SessionLocal``. Anything committing mid-test — ``reconcile_founders``
with ``dry_run=False`` does — permanently mutated real rows: it rewrote location columns on
every founder and hard-deleted the duplicates it merged. Twelve stray "Ada Lovelace" founders
left in the dev DB were the visible residue.

Two mechanisms, both required:
  1. ``DATABASE_URL`` is redirected to a separate database *before* any ``app`` import, so both
     ``app.db.engine`` and ``alembic/env.py`` (which reads ``settings.database_url``) bind to it.
  2. ``SessionLocal`` is re-bound per test to one connection holding an open transaction, using
     ``join_transaction_mode="create_savepoint"`` so an inner ``commit()`` only releases a
     savepoint. The outer transaction is rolled back, so committed writes never survive a test.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import psycopg
import pytest
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
ROOT_ENV = BACKEND_DIR.parent / ".env"
load_dotenv(ROOT_ENV)

_DEV_URL = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://vcbrain:vcbrain@localhost:5433/vcbrain"
)
TEST_DB_NAME = os.environ.get("TEST_DB_NAME", "vcbrain_test")


def _with_database(url: str, name: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, f"/{name}", parts.query, parts.fragment))


def _libpq(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


TEST_URL = _with_database(_DEV_URL, TEST_DB_NAME)

# Redirect before any `app` module is imported; app.db builds its engine at import time.
# Unconditional on purpose: the suite must never be able to reach the dev database.
os.environ["DATABASE_URL"] = TEST_URL


def _create_test_database() -> None:
    with psycopg.connect(_libpq(_with_database(_DEV_URL, "postgres")), autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s", (TEST_DB_NAME,)
        ).fetchone()
        if not exists:
            conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')


def _migrate() -> None:
    from alembic.config import Config

    from alembic import command

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _test_database() -> None:
    """Create and migrate the dedicated test database once per session."""
    assert os.environ["DATABASE_URL"] == TEST_URL, "test DB redirect must happen before app import"
    _create_test_database()
    _migrate()


@pytest.fixture()
def dev_db():
    """Read-only session against the shared dev DB, for ``@pytest.mark.dev_bed`` tests.

    The eval bed deliberately validates live-sourced rows, so those tests cannot use the empty
    test database. The transaction is explicitly READ ONLY so a bed test can never mutate dev data.
    """
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    engine = create_engine(_DEV_URL, pool_pre_ping=True)
    connection = engine.connect()
    connection.execute(text("SET TRANSACTION READ ONLY"))
    session = Session(bind=connection)
    try:
        yield session
    finally:
        session.close()
        connection.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture(autouse=True)
def db_transaction(_test_database):
    """Bind SessionLocal to one rolled-back transaction for the duration of a test."""
    from app.db import SessionLocal, engine

    connection = engine.connect()
    transaction = connection.begin()
    SessionLocal.configure(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield connection
    finally:
        SessionLocal.configure(bind=engine, join_transaction_mode="conditional_savepoint")
        transaction.rollback()
        connection.close()
