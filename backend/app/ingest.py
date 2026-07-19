"""The core scraping primitive: idempotent signal insert.

Dedupe happens at write time via ON CONFLICT (source, external_id) DO NOTHING,
so re-polling a source never creates duplicates.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.connectors.base import SignalEnvelope
from app.models import Signal


def upsert_signal(db: Session, env: SignalEnvelope) -> tuple[Signal, bool]:
    """Insert one signal. Returns (signal, created). created=False → already ingested."""
    new_id = uuid.uuid4()
    stmt = (
        insert(Signal)
        .values(
            id=new_id,
            source=env.source,
            signal_type=env.signal_type,
            external_id=env.external_id,
            entity_hint=env.entity_hint,
            url=env.url,
            title=env.title,
            summary=env.summary,
            occurred_at=env.occurred_at,
            source_reliability=env.source_reliability,
            raw=env.raw,
        )
        .on_conflict_do_nothing(index_elements=["source", "external_id"])
        .returning(Signal.id)
    )
    inserted = db.execute(stmt).first()
    db.commit()

    if inserted is not None:
        return db.get(Signal, new_id), True

    existing = db.execute(
        select(Signal).where(Signal.source == env.source, Signal.external_id == env.external_id)
    ).scalar_one()
    return existing, False
