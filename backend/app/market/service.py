"""Market-research service: validate opportunity -> load thesis -> run graph -> persist.

Runs in the triggered/diligence loop. Precondition: the opportunity has an idea/sector to size
(pre-idea founders have no market to research). The endpoint + a manual run call this.
"""

from sqlalchemy.orm import Session

from app.market.graph import build_market_graph
from app.market.persist import persist_market
from app.market.schemas import OpportunityInput
from app.models import Opportunity
from app.sourcing.service import load_thesis


def _opp_from_row(row: Opportunity) -> dict:
    return {
        "founder_id": str(row.founder_id) if row.founder_id else None,
        "company_name": row.company_name,
        "idea": row.idea or "",
        "sector": row.sector,
        "geo": row.geo,
    }


def run_market_analysis(db: Session, opp: dict | None = None, opportunity_id=None) -> dict:
    """Analyze the market for an opportunity. Pass a dict (creates the opportunity) OR an
    opportunity_id (re-runs against an existing row). Returns a structured result + persist summary.
    """
    if opportunity_id is not None:
        row = db.get(Opportunity, opportunity_id)
        if row is None:
            raise ValueError(f"opportunity {opportunity_id} not found")
        opp = _opp_from_row(row)
    if opp is None:
        raise ValueError("run_market_analysis needs either an opp dict or an opportunity_id")

    subject = OpportunityInput(**opp)  # validates shape
    if not subject.has_subject():
        raise ValueError(
            "market research needs an idea or sector — pre-idea founders have no market to size"
        )

    thesis = load_thesis(db)
    graph = build_market_graph()
    state = graph.invoke({"opportunity": subject.model_dump(), "thesis": thesis, "trace": []})

    analysis = {
        "opportunity": subject.model_dump(),
        "sizing": state.get("sizing") or {},
        "competition": state.get("competition") or {},
        "comparables": state.get("comparables") or {},
        "kpi": state.get("kpi") or {},
        "synthesis": state.get("synthesis") or {},
        "hits_by_goal": state.get("hits_by_goal") or {},
    }
    summary = persist_market(db, analysis, opportunity_id=opportunity_id)
    summary["stats"] = state.get("stats", {})
    summary["trace"] = state.get("trace", [])
    summary["analysis"] = analysis
    return summary
