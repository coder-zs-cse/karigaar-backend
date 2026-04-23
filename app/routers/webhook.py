import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.schemas.webhook import BolnaWebhookPayload, OKResponse
from app.services.webhook_processor import handle_webhook

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhook"])


@router.post("/bolna", response_model=OKResponse)
async def bolna_webhook(
    request: Request,
    db: Session = Depends(get_db),
) -> OKResponse:
    """
    Receives all Bolna post-call webhook events for all 5 agents (both accounts).

    Multiple events per call are expected. Each event is merged (by bolna_call_id)
    into the same call_logs row. Actual DB mutations (workers/customers/jobs)
    are applied only once per call — after extracted_data arrives and before
    the `processed` flag is set.

    Always returns HTTP 200 so Bolna does not retry the same event.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    try:
        payload = BolnaWebhookPayload.model_validate(body)
    except Exception as exc:
        logger.error("Webhook validation error: %s", exc)
        raise HTTPException(status_code=422, detail=str(exc))

    logger.info(
        "Webhook received | call_id=%s agent_id=%s status=%s has_extracted=%s",
        payload.id,
        payload.agent_id,
        payload.status,
        bool(payload.extracted_data),
    )

    try:
        await handle_webhook(payload, db)
    except Exception as exc:
        logger.error(
            "Webhook processing error | call_id=%s error=%s",
            payload.id, exc, exc_info=True,
        )
        return OKResponse(status="error", detail=str(exc))

    return OKResponse(status="ok")
