"""Sync reference data (sourcing channels + default thesis) from code on startup.

Channels (seeds.py) and the default thesis (thesis.py) are code-defined until a settings UI
exists, so we reconcile the DB to match on boot — not seed-once — otherwise edits to those
files never reach the running system. Guard this once the thesis becomes UI-editable.
"""

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import InvestmentThesis, SourcingChannel
from app.sourcing.seeds import SEED_CHANNELS
from app.sourcing.thesis import DEFAULT_THESIS

_THESIS_NAME = "Munich AI/robotics (demo)"


def sync_reference_data(db: Session) -> None:
    # Channels: replace with the current SEED_CHANNELS (display mirror of the constant).
    db.execute(delete(SourcingChannel))
    for c in SEED_CHANNELS:
        db.add(
            SourcingChannel(
                name=c["name"], type=c["type"], domain=c["domain"], enabled=c["enabled"]
            )
        )

    # Default thesis: keep in sync with DEFAULT_THESIS (code is source of truth for now).
    t = DEFAULT_THESIS
    row = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    if row is None:
        # Create-if-missing only: the thesis is now UI-editable (PUT /thesis), so once a row
        # exists the DB owns it — don't clobber the investor's edits on every boot.
        row = InvestmentThesis(is_default=True)
        db.add(row)
        row.name = _THESIS_NAME
        row.industries = t.industries
        row.geo = t.geo
        row.stage = t.stage
        row.keywords = t.keywords
        row.founder_preferences = t.founder_preferences
    db.commit()
