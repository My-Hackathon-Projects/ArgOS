"""3-axis assembler + screen dispatch (prd item 6).

Orchestrates the three INDEPENDENT axes for an opportunity and persists them as three separate
three_axis rows. There is deliberately NO blended/averaged number anywhere — the disagreement
between the axes IS the product. Manual dispatch only (POST /opportunities/{id}/screen).

Order matters: founder (deterministic) -> market (consumed from app.market, run once & reused)
-> idea (LLM, reads the market row). The market axis is NEVER rebuilt here — we call the market
agent's own entrypoint.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market.service import run_market_analysis
from app.models import Opportunity, ThreeAxis
from app.screening.founder_axis import upsert_founder_axis
from app.screening.idea_axis import upsert_idea_axis


def _market_row(db: Session, opportunity_id: uuid.UUID) -> ThreeAxis | None:
    return (
        db.execute(
            select(ThreeAxis).where(
                ThreeAxis.opportunity_id == opportunity_id, ThreeAxis.axis == "market"
            )
        )
        .scalars()
        .first()
    )


def screen_opportunity(
    db: Session, opportunity_id: uuid.UUID, *, refresh_market: bool = False
) -> Opportunity:
    """Run all applicable axes for an opportunity, persist 3 independent rows, return the opp.

    - founder axis: deterministic, only if the opportunity is founder-linked.
    - market axis: consumed from app.market.run_market_analysis; reused if already present
      (it is the expensive Tavily+LLM step) unless refresh_market=True.
    - idea axis: LLM, reads the founder + market evidence.
    """
    opp = db.get(Opportunity, opportunity_id)
    if opp is None:
        raise ValueError(f"opportunity {opportunity_id} not found")

    # 1. Founder axis (deterministic) — flush; committed alongside the rest below.
    if opp.founder_id is not None:
        upsert_founder_axis(db, opp.id)

    # 2. Market axis — reuse the existing row (expensive to rebuild) unless asked to refresh.
    #    run_market_analysis manages + commits its own transaction.
    if refresh_market or _market_row(db, opp.id) is None:
        run_market_analysis(db, opportunity_id=opp.id)

    # 3. Idea-vs-market axis (LLM) — reads the market row persisted above.
    upsert_idea_axis(db, opp.id)

    opp.status = "diligence"
    db.commit()
    db.refresh(opp)
    return opp
