import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.connectors.base import SignalEnvelope
from app.db import SessionLocal, get_db
from app.ingest import upsert_signal
from app.models import Founder, InvestmentThesis, Signal, SourcingChannel
from app.sourcing.seed_data import sync_reference_data
from app.sourcing.service import run_discovery


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        sync_reference_data(db)  # sourcing channels + default thesis, synced from code
    finally:
        db.close()
    yield


app = FastAPI(title="VC Brain — Sourcing", lifespan=lifespan)


@app.get("/health")
def health(db: Session = Depends(get_db)) -> dict:
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
            "url": s.canonical_url or s.url,
            "source_reliability": s.source_reliability,
            "occurred_at": s.occurred_at,
            "ingested_at": s.ingested_at,
        }
        for s in rows
    ]


@app.post("/signals/ingest")
def ingest(env: SignalEnvelope, db: Session = Depends(get_db)) -> dict:
    signal, created = upsert_signal(db, env)
    return {"id": str(signal.id), "created": created}


# ── Sourcing / outbound ──────────────────────────────────────────────────────
@app.post("/discovery/run")
def discovery_run(db: Session = Depends(get_db)) -> dict:
    """Hand-trigger a discovery run (thesis → search → resolve → persist). Synchronous (~30-60s)."""
    return run_discovery(db)


@app.get("/founders")
def list_founders(db: Session = Depends(get_db)) -> list[dict]:
    rows = (
        db.execute(select(Founder).order_by(Founder.first_discovered_at.desc().nullslast()))
        .scalars()
        .all()
    )
    out = []
    for f in rows:
        n = db.execute(
            select(func.count()).select_from(Signal).where(Signal.founder_id == f.id)
        ).scalar_one()
        out.append(
            {
                "id": str(f.id),
                "display_name": f.display_name,
                "status": f.status,
                "discovery_confidence": f.discovery_confidence,
                "current_company": f.current_company,
                "occupation": f.occupation,
                "city": f.city,
                "signal_count": n,
            }
        )
    return out


@app.get("/founders/{founder_id}")
def get_founder(founder_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    f = db.get(Founder, founder_id)
    if f is None:
        raise HTTPException(status_code=404, detail="founder not found")
    identity = f.identities[0] if f.identities else None
    signals = (
        db.execute(
            select(Signal)
            .where(Signal.founder_id == f.id)
            .order_by(Signal.occurred_at.asc().nullslast())
        )
        .scalars()
        .all()
    )
    return {
        "id": str(f.id),
        "display_name": f.display_name,
        "status": f.status,
        "discovery_confidence": f.discovery_confidence,
        "current_company": f.current_company,
        "occupation": f.occupation,
        "city": f.city,
        "education": f.education,
        "first_discovered_at": f.first_discovered_at,
        "last_checked_at": f.last_checked_at,
        "identity": {
            "github": identity.github if identity else None,
            "twitter": identity.twitter if identity else None,
            "linkedin": identity.linkedin if identity else None,
            "website": identity.website if identity else None,
        },
        "signals": [
            {
                "source": s.source,
                "signal_type": s.signal_type,
                "title": s.title,
                "summary": s.summary,
                "url": s.canonical_url,
                "occurred_at": s.occurred_at,
                "source_reliability": s.source_reliability,
                "resolution_confidence": s.resolution_confidence,
                "resolution_method": s.resolution_method,
            }
            for s in signals
        ],
    }


@app.get("/sourcing-channels")
def list_channels(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(SourcingChannel).order_by(SourcingChannel.name)).scalars().all()
    return [
        {
            "name": c.name,
            "type": c.type,
            "domain": c.domain,
            "enabled": c.enabled,
            "yield_count": c.yield_count,
        }
        for c in rows
    ]


@app.get("/thesis")
def get_thesis(db: Session = Depends(get_db)) -> dict:
    row = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="no default thesis")
    return {
        "name": row.name,
        "industries": row.industries,
        "geo": row.geo,
        "stage": row.stage,
        "keywords": row.keywords,
        "founder_preferences": row.founder_preferences,
    }
