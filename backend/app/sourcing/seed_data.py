"""Idempotent seed of the client-facing sourcing channels + the default thesis."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InvestmentThesis, SourcingChannel
from app.sourcing.seeds import SEED_CHANNELS
from app.sourcing.thesis import DEFAULT_THESIS


def seed_if_empty(db: Session) -> None:
    existing = {name for (name,) in db.execute(select(SourcingChannel.name))}
    for c in SEED_CHANNELS:
        if c["name"] not in existing:
            db.add(
                SourcingChannel(
                    name=c["name"], type=c["type"], domain=c["domain"], enabled=c["enabled"]
                )
            )

    has_default = (
        db.execute(select(InvestmentThesis).where(InvestmentThesis.is_default.is_(True)))
        .scalars()
        .first()
    )
    if has_default is None:
        t = DEFAULT_THESIS
        db.add(
            InvestmentThesis(
                name="Munich AI/robotics (demo)",
                industries=t.industries,
                geo=t.geo,
                stage=t.stage,
                keywords=t.keywords,
                founder_preferences=t.founder_preferences,
                is_default=True,
            )
        )
    db.commit()
