"""
Pydantic schemas for the Bolna post-call webhook.

All fields are Optional because:
  - Intermediate webhook events (e.g. call-disconnected) don't carry extracted_data.
  - Different agents send different extraction groups.
We validate permissively and store every raw payload for audit.
"""

from typing import Any, Optional
from pydantic import BaseModel


# ── Telephony ─────────────────────────────────────────────────────────────────

class TelephonyData(BaseModel):
    duration: Optional[str] = None
    to_number: Optional[str] = None
    from_number: Optional[str] = None
    recording_url: Optional[str] = None
    hosted_telephony: Optional[bool] = None
    provider_call_id: Optional[str] = None
    call_type: Optional[str] = None        # "inbound" | "outbound"
    provider: Optional[str] = None
    hangup_by: Optional[str] = None
    hangup_reason: Optional[str] = None
    hangup_provider_code: Optional[str] = None

    model_config = {"extra": "ignore"}


class ExtractionValue(BaseModel):
    """A single extracted field as returned by Bolna's LLM extraction."""
    subjective: Optional[Any] = None
    confidence: Optional[float] = None
    confidence_label: Optional[str] = None
    reasoning_subjective: Optional[str] = None

    model_config = {"extra": "ignore"}


# ── Top-level webhook payload ─────────────────────────────────────────────────

class BolnaWebhookPayload(BaseModel):
    id: str                                   # Bolna call id — primary key
    agent_id: Optional[str] = None
    status: Optional[str] = None              # "completed", "in-progress", etc.
    smart_status: Optional[str] = None
    conversation_duration: Optional[float] = None
    transcript: Optional[str] = None
    extracted_data: Optional[dict[str, Any]] = None   # raw; parsed per agent
    telephony_data: Optional[TelephonyData] = None
    user_number: Optional[str] = None
    error_message: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    model_config = {"extra": "ignore"}


# ── Generic API response ──────────────────────────────────────────────────────

class OKResponse(BaseModel):
    status: str = "ok"
    detail: Optional[str] = None
