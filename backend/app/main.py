import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_schemas import (
    ChannelItem,
    DiscoveryRunResponse,
    FounderDetail,
    FounderListItem,
    HealthResponse,
    IngestResponse,
    MarketAnalysisResponse,
    MarketOpportunityListItem,
    SignalListItem,
    ThesisResponse,
)
from app.connectors.base import SignalEnvelope
from app.db import SessionLocal, get_db
from app.ingest import upsert_signal
from app.market import read as market_read
from app.models import Founder, InvestmentThesis, Signal, SourcingChannel
from app.sourcing.seed_data import sync_reference_data
from app.sourcing.service import run_discovery

# Next.js dev server. Kept explicit (not "*") so credentialed requests stay allowed.
CORS_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


@asynccontextmanager
async def lifespan(app: FastAPI):
    db = SessionLocal()
    try:
        sync_reference_data(db)  # sourcing channels + default thesis, synced from code
    finally:
        db.close()
    yield


def _operation_id(route: APIRoute) -> str:
    # operationId = handler name -> clean generated FE hooks (useListSignals, useGetFounder, ...).
    return route.name


app = FastAPI(
    title="VC Brain — Sourcing",
    lifespan=lifespan,
    generate_unique_id_function=_operation_id,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> dict:
    count = db.execute(select(func.count()).select_from(Signal)).scalar_one()
    return {"status": "ok", "signals": count}


@app.get("/signals", response_model=list[SignalListItem])
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


@app.post("/signals/ingest", response_model=IngestResponse)
def ingest(env: SignalEnvelope, db: Session = Depends(get_db)) -> dict:
    signal, created = upsert_signal(db, env)
    return {"id": str(signal.id), "created": created}


# ── Sourcing / outbound ──────────────────────────────────────────────────────
@app.post("/discovery/run", response_model=DiscoveryRunResponse)
def discovery_run(db: Session = Depends(get_db)) -> dict:
    """Hand-trigger a discovery run (thesis → search → resolve → persist). Synchronous (~30-60s)."""
    return run_discovery(db)


@app.get("/founders", response_model=list[FounderListItem])
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


@app.get("/founders/{founder_id}", response_model=FounderDetail)
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


@app.get("/sourcing-channels", response_model=list[ChannelItem])
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


# ── Market research ──────────────────────────────────────────────────────────
@app.get("/market/opportunities", response_model=list[MarketOpportunityListItem])
def list_market_opportunities(db: Session = Depends(get_db)) -> list[dict]:
    """Opportunities with a persisted market axis — the research tab's list."""
    return market_read.list_opportunities(db)


@app.get("/market/opportunities/{opportunity_id}", response_model=MarketAnalysisResponse)
def get_market_analysis(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Full market analysis: sizing / competition / comparables / KPI + the market axis."""
    r = market_read.get_analysis(db, opportunity_id)
    if r is None:
        raise HTTPException(status_code=404, detail="market analysis not found")
    return r


@app.get("/thesis", response_model=ThesisResponse)
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
