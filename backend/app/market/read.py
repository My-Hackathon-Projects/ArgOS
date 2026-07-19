"""Read the persisted market analysis back into API response shapes (main.py serves these).

Reshapes the opportunity-anchored claims (market_size|market|competition|comparable) + the
three_axis 'market' row into the memo-section view the frontend renders. Each row carries its
source url (provenance) and reused trust_score.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, ClaimEvidence, Opportunity, Signal, ThreeAxis

_SIZING_ORDER = {"TAM": 0, "SAM": 1, "SOM": 2, "CAGR": 3}


def _first_url(db: Session, claim_id) -> str | None:
    return db.execute(
        select(Signal.url)
        .join(ClaimEvidence, ClaimEvidence.signal_id == Signal.id)
        .where(ClaimEvidence.claim_id == claim_id)
        .limit(1)
    ).scalar()


def _figure(db: Session, c: Claim) -> dict:
    a = c.attributes or {}
    return {
        "metric": a.get("metric"),
        "value": a.get("value"),
        "basis": a.get("basis"),
        "confidence": a.get("confidence"),
        "trust_score": c.trust_score,
        "status": c.status,
        "url": _first_url(db, c.id),
    }


def _axis_view(ax: ThreeAxis | None) -> dict | None:
    if ax is None:
        return None
    return {
        "verdict": ax.verdict,
        "score": ax.score,
        "trend": ax.trend,
        "rationale": ax.rationale,
        "confidence": ax.confidence,
        "gaps": ax.gaps or [],
    }


def list_opportunities(db: Session) -> list[dict]:
    """Opportunities that have a market axis — the list the research tab shows."""
    out = []
    for o in db.execute(select(Opportunity)).scalars().all():
        ax = (
            db.execute(
                select(ThreeAxis).where(
                    ThreeAxis.opportunity_id == o.id, ThreeAxis.axis == "market"
                )
            )
            .scalars()
            .first()
        )
        if ax is None:
            continue
        out.append(
            {
                "id": str(o.id),
                "company_name": o.company_name,
                "sector": o.sector,
                "geo": o.geo,
                "verdict": ax.verdict,
                "score": ax.score,
                "trend": ax.trend,
            }
        )
    return out


def get_analysis(db: Session, opp_id) -> dict | None:
    o = db.get(Opportunity, opp_id)
    if o is None:
        return None
    ax = (
        db.execute(
            select(ThreeAxis).where(ThreeAxis.opportunity_id == o.id, ThreeAxis.axis == "market")
        )
        .scalars()
        .first()
    )
    claims = db.execute(select(Claim).where(Claim.opportunity_id == o.id)).scalars().all()
    sizing, kpi, competitors, comparables = [], [], [], []
    for c in claims:
        a = c.attributes or {}
        if c.category == "market_size":
            sizing.append(_figure(db, c))
        elif c.category == "market":
            kpi.append(_figure(db, c))
        elif c.category == "competition":
            name = c.statement.removeprefix("Competitor: ").split(" — ")[0]
            competitors.append(
                {
                    "name": name,
                    "cluster": a.get("cluster"),
                    "positioning": a.get("positioning"),
                    "is_emerging_threat": bool(a.get("is_emerging_threat")),
                    "trust_score": c.trust_score,
                    "url": _first_url(db, c.id),
                }
            )
        elif c.category == "comparable":
            name = c.statement.removeprefix("Comparable: ").split(" raised ")[0]
            comparables.append(
                {
                    "name": name,
                    "stage": a.get("stage"),
                    "round_size": a.get("round_size"),
                    "valuation": a.get("valuation"),
                    "date": a.get("date"),
                    "similarity_rationale": a.get("similarity_rationale"),
                    "trust_score": c.trust_score,
                    "url": _first_url(db, c.id),
                }
            )
    sizing.sort(key=lambda f: _SIZING_ORDER.get((f["metric"] or "").upper(), 9))
    return {
        "id": str(o.id),
        "company_name": o.company_name,
        "idea": o.idea,
        "sector": o.sector,
        "geo": o.geo,
        "axis": _axis_view(ax),
        "sizing": sizing,
        "kpi": kpi,
        "competitors": competitors,
        "comparables": comparables,
    }
