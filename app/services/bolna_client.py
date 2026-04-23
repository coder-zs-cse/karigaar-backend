"""
Bolna API client.

Wraps POST /call (https://www.bolna.ai/docs/api-reference/calls/make).
Each outbound call targets a specific (line, purpose) pair which resolves
to one of our 5 registered agents.

The 3 outbound agents:
  - (worker, job_offer)     → Agent 2: Arjun — Job Offer
  - (customer, pairing)     → Agent 4: Priya — Pairing
  - (customer, feedback)    → Agent 5: Priya — Feedback
"""

import logging
from typing import Any

import httpx

from app.core.config import AGENT_CONFIG, get_agent_id_by_purpose, settings

logger = logging.getLogger(__name__)


async def trigger_outbound_call(
    *,
    line: str,                    # "worker" | "customer"
    purpose: str,                 # "job_offer" | "pairing" | "feedback"
    recipient_phone: str,
    user_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Place an outbound call via Bolna.

    user_data values are injected into the agent's prompt as {variable}
    references and also used in the welcome message.

    Returns Bolna's response: {"message": "done", "status": "queued", "execution_id": "..."}
    """
    agent_id = get_agent_id_by_purpose(line, purpose)
    cfg = AGENT_CONFIG[agent_id]

    url = f"{settings.bolna_base_url}/call"
    headers = {
        "Authorization": f"Bearer {cfg['api_key']}",
        "Content-Type": "application/json",
    }
    payload: dict[str, Any] = {
        "agent_id": agent_id,
        "recipient_phone_number": recipient_phone,
        "user_data": user_data,
    }
    if cfg.get("from_phone"):
        payload["from_phone_number"] = cfg["from_phone"]

    logger.info(
        "Bolna outbound | line=%s purpose=%s agent_id=%s recipient=%s",
        line, purpose, agent_id, recipient_phone,
    )

    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(url, headers=headers, json=payload)
        resp.raise_for_status()
        result = resp.json()

    logger.info(
        "Bolna outbound queued | execution_id=%s status=%s",
        result.get("execution_id"), result.get("status"),
    )
    return result
