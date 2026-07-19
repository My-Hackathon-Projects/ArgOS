"""Fixed eval subjects (prd item 1) — the reproducible bed every LLM quality loop runs against.

Real rows minted by the real pipeline (app.sourcing.discover -> app.claims.run ->
POST /opportunities), never synthetic. The ids are FROZEN on purpose: judge scores are only
comparable across iterate rounds if the subjects never move. If a row disappears from the DB,
validate_subjects() crashes loudly — reseed deliberately, don't silently swap subjects.

No contradiction subject yet: the claims layer can mint one (stance='refutes' ->
status='contradicted') but the wild hasn't supplied conflicting evidence for these founders.
Tracked in ralph/plans/human-backlog.txt; validate_subjects() reports the bool so item-2's
harness can surface it on every scorecard.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Claim, Founder, Opportunity
from app.screening.founder_axis import BULL_AT_LEAST, COLD_START_MIN_CLAIMS


@dataclass(frozen=True)
class Subject:
    id: uuid.UUID
    label: str
    why: str


FOUNDER_SUBJECTS: tuple[Subject, ...] = (
    Subject(
        uuid.UUID("4ec6c740-719f-4a70-9702-942eeb109572"),
        "Christiam Ipanaque",
        "strong: top Founder Score in DB (~44.5, bull band), 22 claims "
        "(LangGraph/RAG/agents + authored 'Build and Deploy Production AI Systems')",
    ),
    Subject(
        uuid.UUID("6b982182-d2be-4569-a4ce-8f672a39a1cb"),
        "Andrea Gentilini",
        "mid-band: score ~22 on 8 claims — above the cold-start floor yet clearly neutral; "
        "the axis/memo must not inflate this into conviction",
    ),
    Subject(
        uuid.UUID("3e7f74f1-553e-4d28-98ac-2b466a752cf0"),
        "Tanmay Baranwal",
        "cold-start: 5 claims (< COLD_START_MIN_CLAIMS) — limited evidence must read as "
        "low CONFIDENCE, never as a low-score bear verdict",
    ),
)

OPPORTUNITY_SUBJECTS: tuple[Subject, ...] = (
    Subject(
        uuid.UUID("d60ed564-f8d1-448b-a4ca-839ed261f409"),
        "Ipanaque Labs",
        "strong-founder-linked (Christiam): agent-orchestration platform idea grounded in his "
        "real claim footprint — the bull-case screening subject",
    ),
    Subject(
        uuid.UUID("2392aa75-ba72-4d6b-8467-3922fb58b175"),
        "Ticky Tech",
        "cold-start-founder-linked (Tanmay): devtools idea on thin evidence — exercises "
        "uncertainty handling end-to-end",
    ),
    Subject(
        uuid.UUID("a8450afa-6742-4abb-a11b-592c775e1c09"),
        "Nimbus Edge",
        "founderless with 20 opportunity-anchored market claims + a persisted market axis — "
        "exercises the market/memo path and the no-founder edge",
    ),
)

# Keep the bed small so generate+judge rounds stay cheap (PRD: 2-3 each).
assert 2 <= len(FOUNDER_SUBJECTS) <= 3 and 2 <= len(OPPORTUNITY_SUBJECTS) <= 3


def validate_subjects(
    db: Session,
    founders: tuple[Subject, ...] = FOUNDER_SUBJECTS,
    opportunities: tuple[Subject, ...] = OPPORTUNITY_SUBJECTS,
) -> dict:
    """Assert every subject resolves + the bed keeps its coverage properties; return the
    resolved summary for run_eval to log. Crashes (fail-fast) if the bed degraded — never
    silently run quality rounds against missing or shifted data.
    """
    founder_rows = []
    for s in founders:
        f = db.get(Founder, s.id)
        if f is None:
            raise RuntimeError(f"eval founder {s.label} ({s.id}) not in DB — bed degraded")
        n_claims = db.execute(
            select(func.count()).select_from(Claim).where(Claim.founder_id == s.id)
        ).scalar_one()
        if n_claims == 0:
            raise RuntimeError(f"eval founder {s.label} ({s.id}) has 0 claims — run app.claims.run")
        founder_rows.append(
            {
                "id": str(s.id),
                "label": s.label,
                "why": s.why,
                "founder_score": f.founder_score,
                "n_claims": n_claims,
                "cold_start": n_claims < COLD_START_MIN_CLAIMS,
            }
        )
    if not any(r["cold_start"] for r in founder_rows):
        raise RuntimeError("eval bed lost its cold-start founder — coverage property broken")
    if not any(
        r["founder_score"] is not None and r["founder_score"] >= BULL_AT_LEAST
        for r in founder_rows
    ):
        raise RuntimeError("eval bed lost its bull-band founder — coverage property broken")

    founder_ids = {r["id"] for r in founder_rows}
    opportunity_rows = []
    for s in opportunities:
        o = db.get(Opportunity, s.id)
        if o is None:
            raise RuntimeError(f"eval opportunity {s.label} ({s.id}) not in DB — bed degraded")
        if not ((o.idea or "").strip() or (o.sector or "").strip()):
            raise RuntimeError(f"eval opportunity {s.label} ({s.id}) has neither idea nor sector")
        if o.founder_id is not None and str(o.founder_id) not in founder_ids:
            # Idea-axis eval reads the opportunity's founder claims — a linked founder outside
            # FOUNDER_SUBJECTS would score against claims the bed doesn't track.
            raise RuntimeError(
                f"eval opportunity {s.label} links founder {o.founder_id} not in FOUNDER_SUBJECTS"
            )
        opportunity_rows.append(
            {
                "id": str(s.id),
                "label": s.label,
                "why": s.why,
                "founder_id": str(o.founder_id) if o.founder_id else None,
                "idea": o.idea,
                "sector": o.sector,
                "status": o.status,
            }
        )
    if not any(r["founder_id"] for r in opportunity_rows):
        raise RuntimeError("eval bed needs >=1 founder-linked opportunity for the idea axis")

    contradicted = db.execute(
        select(func.count())
        .select_from(Claim)
        .where(Claim.founder_id.in_([s.id for s in founders]), Claim.status == "contradicted")
    ).scalar_one()
    return {
        "founders": founder_rows,
        "opportunities": opportunity_rows,
        "has_contradiction_subject": contradicted > 0,
    }
