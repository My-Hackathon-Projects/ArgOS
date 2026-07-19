import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.routing import APIRoute
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api_schemas import (
    ApplyResponse,
    ChannelItem,
    DecisionRequest,
    DiscoveryRunResponse,
    FounderDetail,
    FounderListItem,
    HealthResponse,
    IngestResponse,
    MarketAnalysisResponse,
    MarketOpportunityListItem,
    MemoView,
    OpportunityCreate,
    OpportunityDetail,
    OpportunityListItem,
    OutreachDraft,
    SignalListItem,
    ThesisResponse,
    ThesisUpdate,
)
from app.config import settings
from app.connectors.base import SignalEnvelope
from app.db import SessionLocal, get_db
from app.inbound.service import run_inbound_application
from app.ingest import upsert_signal
from app.market import read as market_read
from app.memo.generate import generate_memo
from app.models import (
    Claim,
    Founder,
    InvestmentThesis,
    Memo,
    Opportunity,
    Signal,
    SourcingChannel,
)
from app.outbound.draft import draft_outreach
from app.screening.assemble import screen_opportunity
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
    scheduler = None
    if settings.cron_enabled:
        from app.scheduler import start_scheduler

        scheduler = start_scheduler()
        print(
            f"[cron] active — discovery every {settings.discovery_interval_min}min, "
            f"refresh every {settings.refresh_interval_min}min (claims registered, paused)"
        )
    yield
    if scheduler is not None:
        scheduler.shutdown(wait=False)


def _operation_id(route: APIRoute) -> str:
    # operationId = handler name -> clean generated FE hooks (useListSignals, useGetFounder, ...).
    return route.name


app = FastAPI(
    title="ArgOS",
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


# ── Inbound intake ───────────────────────────────────────────────────────────
@app.post("/apply", response_model=ApplyResponse, status_code=201)
def apply_inbound(
    deck: UploadFile = File(..., description="Pitch deck PDF"),
    company_name: str = Form(..., min_length=1),
    db: Session = Depends(get_db),
) -> dict:
    """Inbound application intake: deck PDF + company name -> opportunity + per-page signals +
    claims + prescreen. Synchronous (~10-20s: one extraction + one prescreen call, fast model).
    Full 3-axis screening stays manual-dispatch via POST /opportunities/{id}/screen."""
    if deck.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="deck must be a PDF")
    deck_bytes = deck.file.read()
    if not deck_bytes:
        raise HTTPException(status_code=422, detail="deck file is empty")
    try:
        return run_inbound_application(db, company_name=company_name, deck_bytes=deck_bytes)
    except ValueError as e:  # unparseable / text-free deck, blank company name
        raise HTTPException(status_code=422, detail=str(e)) from e


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
                "founder_score": f.founder_score,
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
    claims = (
        db.execute(
            select(Claim)
            .where(Claim.founder_id == f.id)
            .order_by(Claim.trust_score.desc().nullslast())
        )
        .scalars()
        .all()
    )
    return {
        "id": str(f.id),
        "display_name": f.display_name,
        "status": f.status,
        "discovery_confidence": f.discovery_confidence,
        "founder_score": f.founder_score,
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
        "claims": [
            {
                "statement": c.statement,
                "category": c.category,
                "trust_score": c.trust_score,
                "status": c.status,
                "evidence_count": len(c.evidence),
                "supporting_count": sum(1 for e in c.evidence if e.stance == "supports"),
                "refuting_count": sum(1 for e in c.evidence if e.stance == "refutes"),
                "updated_at": c.updated_at,
            }
            for c in claims
        ],
    }


@app.post("/founders/{founder_id}/outreach", response_model=OutreachDraft)
def outreach(founder_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """ACTIVATE — draft a (mocked) cold-outreach email to a sourced founder. Not actually sent."""
    try:
        return draft_outreach(db, founder_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


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


# ── Opportunities (manual-dispatch entry for screening/memo) ─────────────────
_AXIS_ORDER = {"founder": 0, "market": 1, "idea": 2}


def _opportunity_dict(opp: Opportunity) -> dict:
    return {
        "id": str(opp.id),
        "founder_id": str(opp.founder_id) if opp.founder_id else None,
        "company_name": opp.company_name,
        "idea": opp.idea,
        "sector": opp.sector,
        "geo": opp.geo,
        "status": opp.status,
        "created_at": opp.created_at,
        "decision": opp.decision,
        "axes": [
            {
                "axis": a.axis,
                "score": a.score,
                "verdict": a.verdict,
                "trend": a.trend,
                "confidence": a.confidence,
                "rationale": a.rationale,
                "evidence": a.evidence,
                "gaps": a.gaps or [],
            }
            for a in sorted(opp.axes, key=lambda a: _AXIS_ORDER[a.axis])
        ],
    }


@app.post("/opportunities", response_model=OpportunityDetail, status_code=201)
def create_opportunity(body: OpportunityCreate, db: Session = Depends(get_db)) -> dict:
    if body.founder_id is not None and db.get(Founder, body.founder_id) is None:
        raise HTTPException(status_code=404, detail="founder not found")
    opp = Opportunity(
        founder_id=body.founder_id,
        company_name=body.company_name,
        idea=(body.idea or "").strip() or None,
        sector=(body.sector or "").strip() or None,
        geo=body.geo,
    )
    db.add(opp)
    db.commit()
    db.refresh(opp)
    return _opportunity_dict(opp)


@app.get("/opportunities", response_model=list[OpportunityListItem])
def list_opportunities(db: Session = Depends(get_db)) -> list[dict]:
    rows = db.execute(select(Opportunity).order_by(Opportunity.created_at.desc())).scalars().all()
    return [_opportunity_dict(o) for o in rows]


@app.get("/opportunities/{opportunity_id}", response_model=OpportunityDetail)
def get_opportunity(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return _opportunity_dict(opp)


@app.post("/opportunities/{opportunity_id}/screen", response_model=OpportunityDetail)
def screen(
    opportunity_id: uuid.UUID,
    refresh_market: bool = False,
    db: Session = Depends(get_db),
) -> dict:
    """Manual-dispatch 3-axis screening: founder (deterministic) + market (consumed) + idea (LLM),
    persisted as 3 independent rows — never averaged. Reuses market axis unless refresh_market."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    screen_opportunity(db, opportunity_id, refresh_market=refresh_market)
    db.expire_all()
    refreshed = db.get(Opportunity, opportunity_id)
    if refreshed is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return _opportunity_dict(refreshed)


def _memo_dict(m: Memo) -> dict:
    return {
        "opportunity_id": str(m.opportunity_id),
        "sections": m.sections,
        "recommendation": m.recommendation,
        "confidence": m.confidence,
        "gaps": m.gaps or [],
        "quality": m.quality,
        "generated_at": m.generated_at,
    }


@app.post("/opportunities/{opportunity_id}/memo", response_model=MemoView)
def create_memo(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    """Generate (or regenerate) the mini investment memo — requires the opportunity be screened."""
    if db.get(Opportunity, opportunity_id) is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    return _memo_dict(generate_memo(db, opportunity_id))


@app.get("/opportunities/{opportunity_id}/memo", response_model=MemoView)
def get_memo(opportunity_id: uuid.UUID, db: Session = Depends(get_db)) -> dict:
    row = db.execute(select(Memo).where(Memo.opportunity_id == opportunity_id)).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="memo not generated yet")
    return _memo_dict(row)


# pursue -> committed, track -> keep in diligence, pass -> rejected
_DECISION_STATUS = {"pursue": "decided", "track": "diligence", "pass": "rejected"}


@app.post("/opportunities/{opportunity_id}/decision", response_model=OpportunityDetail)
def decide(
    opportunity_id: uuid.UUID, body: DecisionRequest, db: Session = Depends(get_db)
) -> dict:
    """Record the investor's decision (pursue|track|pass) — the funnel's Decision step. Stamps
    decided_at (signal->decision latency) and moves the opportunity's status."""
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise HTTPException(status_code=404, detail="opportunity not found")
    opp.decision = body.decision
    opp.status = _DECISION_STATUS[body.decision]
    opp.decided_at = datetime.now(UTC)
    db.commit()
    db.refresh(opp)
    return _opportunity_dict(opp)


def _thesis_dict(row: InvestmentThesis) -> dict:
    return {
        "name": row.name,
        "industries": row.industries,
        "geo": row.geo,
        "stage": row.stage,
        "keywords": row.keywords,
        "founder_preferences": row.founder_preferences,
        "check_size": row.check_size,
        "ownership": row.ownership,
        "risk": row.risk,
        "free_text": row.free_text,
    }


def _default_thesis(db: Session) -> InvestmentThesis | None:
    return (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )


@app.get("/thesis", response_model=ThesisResponse)
def get_thesis(db: Session = Depends(get_db)) -> dict:
    row = _default_thesis(db)
    if row is None:
        raise HTTPException(status_code=404, detail="no default thesis")
    return _thesis_dict(row)


@app.put("/thesis", response_model=ThesisResponse)
def update_thesis(body: ThesisUpdate, db: Session = Depends(get_db)) -> dict:
    """Update the default investment thesis — the investor's customizable lens. The DB owns it
    (boot-sync no longer overwrites an existing row), so edits persist across restarts."""
    row = _default_thesis(db)
    if row is None:
        row = InvestmentThesis(is_default=True)
        db.add(row)
    row.name = body.name
    row.industries = body.industries
    row.geo = body.geo
    row.stage = body.stage
    row.keywords = body.keywords
    row.founder_preferences = body.founder_preferences
    row.check_size = body.check_size
    row.ownership = body.ownership
    row.risk = body.risk
    row.free_text = body.free_text
    db.commit()
    db.refresh(row)
    return _thesis_dict(row)
