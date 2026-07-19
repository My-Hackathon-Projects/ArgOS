from fastapi import Depends, FastAPI
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import SignalEnvelope
from app.db import get_db
from app.ingest import upsert_signal
from app.models import Signal

app = FastAPI(title="VC Brain — Sourcing")


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
    # Touches the DB so a green /health also proves connectivity + migrations.
    count = db.execute(select(func.count()).select_from(Signal)).scalar_one()
    return {"status": "ok", "signals": count}


@app.get("/signals")
def list_signals(limit: int = 50, db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.execute(select(Signal).order_by(Signal.ingested_at.desc()).limit(limit)).scalars().all()
    )
    return [
        {
            "id": str(s.id),
            "source": s.source,
            "signal_type": s.signal_type,
            "title": s.title,
            "summary": s.summary,
            "url": s.url,
            "occurred_at": s.occurred_at,
            "ingested_at": s.ingested_at,
        }
        for s in rows
    ]


@app.post("/signals/ingest")
def ingest(env: SignalEnvelope, db: Session = Depends(get_db)) -> dict:
    signal, created = upsert_signal(db, env)
    return {"id": str(signal.id), "created": created}
