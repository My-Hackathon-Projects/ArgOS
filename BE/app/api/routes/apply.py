"""POST /apply — inbound application intake.

Bare-minimum input (hard rule #9): a pitch-deck PDF + the company name.
The endpoint stores the deck, creates the funnel row (stage="received"),
and runs the inbound graph as a background task so the response returns
in <1s; progress is observable via checkpoints on thread
``in:{opportunity_id}``.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile

from app.service.inboud_pipeline.agent import start_inbound_run
from app.service.inboud_pipeline.utils import tools
from app.service.inboud_pipeline.utils.models import OpportunityRecord
from app.service.models import Thesis

router = APIRouter(tags=["apply"])


@router.post("/apply")
async def apply(
    background_tasks: BackgroundTasks,
    deck: UploadFile = File(..., description="Pitch deck PDF"),
    company_name: str = Form(..., min_length=1),
) -> dict[str, str]:
    if deck.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail="Deck must be a PDF")
    deck_bytes = await deck.read()
    if not deck_bytes:
        raise HTTPException(status_code=422, detail="Deck file is empty")

    opportunity_id = uuid.uuid4().hex[:12]
    now = datetime.now(UTC).isoformat()

    # Funnel row exists before the graph runs — every later write (signals,
    # claims, rejections) has its FK target.
    # TODO(thesis): default-empty Thesis until PUT /thesis exists; hard
    # filters self-skip when empty.
    thesis = Thesis()
    tools.save_opportunity(
        OpportunityRecord(
            opportunity_id=opportunity_id,
            track="inbound",
            stage="received",
            thesis_json=thesis.model_dump(),
            created_at=now,
            updated_at=now,
        )
    )
    background_tasks.add_task(
        start_inbound_run, opportunity_id, company_name, deck_bytes, thesis
    )
    return {"opportunity_id": opportunity_id, "status": "running"}
