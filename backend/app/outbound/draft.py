"""Outbound activation — draft a (mocked) cold-outreach email to an identified founder.

The ACTIVATE step of the brief's identify -> activate -> converge. LLM-drafts a cold email from
the founder's corroborated claims + the fund thesis; it is NOT actually sent (mocked). Fast model.
"""

from typing import cast

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, Founder
from app.screening.llm import structured_llm
from app.sourcing.service import load_thesis


class _Draft(BaseModel):
    subject: str = Field(description="A short, specific, non-spammy cold-email subject line.")
    body: str = Field(
        description="A warm, concise cold email (120-160 words), specific to this founder's "
        "actual work, signed off by the fund. Human, not salesy."
    )
    rationale: str = Field(description="One line: why this founder fits the thesis (the hook).")


def draft_outreach(db: Session, founder_id) -> dict:
    f = db.get(Founder, founder_id)
    if f is None:
        raise ValueError(f"founder {founder_id} not found")
    thesis = load_thesis(db)
    claims = (
        db.execute(
            select(Claim)
            .where(Claim.founder_id == f.id)
            .order_by(Claim.trust_score.desc().nullslast())
        )
        .scalars()
        .all()
    )
    highlights = (
        "\n".join(f"- {c.statement}" for c in claims[:6]) or "- (no corroborated claims yet)"
    )
    prompt = f"""<role>You are a partner at the fund below writing a genuine, specific cold-outreach
email to a founder you sourced. Warm, concise, non-generic — reference their real work.</role>

<fund>
name: {thesis.get("name") or "our fund"}
industries: {thesis.get("industries")}
stage: {thesis.get("stage")}
geo: {thesis.get("geo")}
</fund>

<founder>
name: {f.display_name}
occupation: {f.occupation}
company: {f.current_company or "building (pre-company)"}
what we found:
{highlights}
</founder>

<task>
Draft a cold email: a specific subject line, a 120-160 word body that references their actual work
and why the fund is a fit, signed off by the fund, plus a one-line rationale (the hook).
Do NOT invent facts beyond what is given. Keep it human, not salesy.
</task>"""
    out = cast(_Draft, structured_llm(_Draft, smart=False).invoke(prompt))
    return {
        "founder_id": str(f.id),
        "to_name": f.display_name,
        "subject": out.subject,
        "body": out.body,
        "rationale": out.rationale,
    }
