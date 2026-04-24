import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.core.config import get_agent_config
from app.db.database import get_db
from app.schemas.context import CustomerInboundContext, WorkerInboundContext
from app.services.caller_context_service import (
    get_customer_inbound_context,
    get_worker_inbound_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/caller-context", tags=["Caller Context"])


@router.get(
    "",
    response_model=WorkerInboundContext | CustomerInboundContext,
    summary="Pre-call prompt variable injection for Bolna inbound agents",
)
def caller_context(
    contact_number: str = Query(..., description="Caller phone in E.164 format"),
    agent_id: str = Query(..., description="Bolna agent_id making this request"),
    db: Session = Depends(get_db),
) -> WorkerInboundContext | CustomerInboundContext:
    cfg = get_agent_config(agent_id)
    line = cfg.get("line")
    purpose = cfg.get("purpose")

    logger.info(
        "Caller context REQUEST | phone=%s agent_id=%s line=%s purpose=%s",
        contact_number, agent_id, line, purpose,
    )

    if purpose != "inbound":
        logger.warning(
            "caller-context called for non-inbound agent %s (purpose=%s)",
            agent_id, purpose,
        )

    if line == "worker":
        result = get_worker_inbound_context(contact_number, db)
    elif line == "customer":
        result = get_customer_inbound_context(contact_number, db)
    else:
        logger.warning("Unknown agent_id=%s — returning new_customer default", agent_id)
        result = CustomerInboundContext(scenario="new_customer")

    logger.info(
        "Caller context RESPONSE | phone=%s line=%s → %s",
        contact_number, line, result.model_dump_json(),
    )

    return result
