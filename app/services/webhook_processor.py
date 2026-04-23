"""
Webhook processor — incremental, idempotent handler for all 5 agents.

Design:
  1. UPSERT on call_logs keyed by bolna_call_id. Every webhook event merges
     into the same row, overwriting only the fields that are present.
  2. `processed` flag on the row prevents double-application of DB mutations
     if Bolna sends extracted_data in multiple events or we re-receive it.
  3. We only apply DB mutations (workers/customers/jobs) after BOTH of:
       a. extracted_data has arrived (at least once), AND
       b. `processed` is still 0.
  4. Dispatch is based on agent_purpose (from AGENT_CONFIG), not on the
     extraction payload. This means each agent's webhook is routed
     unambiguously to its own handler.

Each handler knows exactly which extraction keys to expect for its agent.
Unknown enum values, missing fields, or empty payloads are handled gracefully.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.core.config import get_agent_config
from app.models import CallLog, Customer, Job, Worker
from app.schemas.webhook import BolnaWebhookPayload

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _extract(extracted_data: dict, key: str) -> Optional[str]:
    """
    Search all extracted_data groups for the first matching field key.

    Expected shape:
        { "group_name": { "field_name": { "subjective": <value>, ... } } }

    Returns the first matched field's .subjective value as a stripped string,
    or None if missing/blank.
    """
    if not extracted_data or not isinstance(extracted_data, dict):
        return None

    for group_fields in extracted_data.values():
        if not isinstance(group_fields, dict):
            continue
        field = group_fields.get(key)
        if not isinstance(field, dict):
            continue
        val = field.get("subjective")
        if val is None:
            continue
        s = str(val).strip()
        if s:
            return s

    return None


def _caller_phone(payload: BolnaWebhookPayload) -> str:
    # if payload.telephony_data and payload.telephony_data.from_number:
    #     return payload.telephony_data.from_number
    return payload.user_number or ""


def _direction(payload: BolnaWebhookPayload) -> Optional[str]:
    if payload.telephony_data and payload.telephony_data.call_type:
        d = payload.telephony_data.call_type
        if d in ("inbound", "outbound"):
            return d
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Entry point — upsert + dispatch
# ─────────────────────────────────────────────────────────────────────────────

async def handle_webhook(payload: BolnaWebhookPayload, db: Session) -> None:
    """
    Called once per incoming Bolna webhook event.
    """
    agent_id = payload.agent_id or ""
    agent_cfg = get_agent_config(agent_id)
    agent_line = agent_cfg.get("line")
    agent_purpose = agent_cfg.get("purpose")

    # ── 1. UPSERT call_logs — merge only non-None fields ──────────────────────
    log = db.query(CallLog).filter(CallLog.bolna_call_id == payload.id).first()
    is_new = log is None

    if is_new:
        log = CallLog(
            bolna_call_id=payload.id,
            bolna_agent_id=agent_id,
            agent_line=agent_line if agent_line in ("worker", "customer") else None,
            agent_purpose=agent_purpose,
            direction=_direction(payload),
            caller_phone=_caller_phone(payload),
            agent_phone=payload.telephony_data.to_number if payload.telephony_data else None,
            call_status=payload.status,
            smart_status=payload.smart_status,
            hangup_reason=payload.telephony_data.hangup_reason if payload.telephony_data else None,
            conversation_duration=payload.conversation_duration,
            transcript=payload.transcript,
            extracted_data=payload.extracted_data,
            processed=0,
            events=[payload.model_dump()],
        )
        db.add(log)
    else:
        # Merge incrementally — only overwrite fields that are present in this event
        if agent_id:
            log.bolna_agent_id = agent_id
        if agent_line in ("worker", "customer"):
            log.agent_line = agent_line
        if agent_purpose:
            log.agent_purpose = agent_purpose
        direction = _direction(payload)
        if direction:
            log.direction = direction
        caller = _caller_phone(payload)
        if caller:
            log.caller_phone = caller
        if payload.telephony_data:
            if payload.telephony_data.to_number:
                log.agent_phone = payload.telephony_data.to_number
            if payload.telephony_data.hangup_reason:
                log.hangup_reason = payload.telephony_data.hangup_reason
        if payload.status:
            log.call_status = payload.status
        if payload.smart_status:
            log.smart_status = payload.smart_status
        if payload.conversation_duration is not None:
            log.conversation_duration = payload.conversation_duration
        if payload.transcript:
            log.transcript = payload.transcript
        if payload.extracted_data:
            log.extracted_data = payload.extracted_data  # latest wins (richer)
        # Append this event to the audit trail
        events = list(log.events or [])
        events.append(payload.model_dump())
        log.events = events

    db.flush()

    # ── 2. Skip DB mutations if no extracted_data yet ────────────────────────
    if not log.extracted_data:
        logger.info(
            "Webhook %s | status=%s | no extracted_data yet — logged only",
            payload.id, log.call_status,
        )
        db.commit()
        return

    # ── 3. Idempotency: skip mutations if already processed ──────────────────
    # if log.processed:
    #     logger.info(
    #         "Webhook %s | already processed — log merged only",
    #         payload.id,
    #     )
    #     db.commit()
    #     return

    # ── 4. Dispatch by agent purpose ─────────────────────────────────────────
    caller_phone = log.caller_phone or ""
    logger.info(
        "Processing | call=%s line=%s purpose=%s phone=%s",
        payload.id, agent_line, agent_purpose, caller_phone,
    )

    try:
        if agent_line == "worker" and agent_purpose == "inbound":
            await _handle_worker_inbound(log, caller_phone, db)
        elif agent_line == "worker" and agent_purpose == "job_offer":
            await _handle_job_offer(log, caller_phone, db)
        elif agent_line == "customer" and agent_purpose == "inbound":
            await _handle_customer_inbound(log, caller_phone, db)
        elif agent_line == "customer" and agent_purpose == "pairing":
            await _handle_pairing(log, caller_phone, db)
        elif agent_line == "customer" and agent_purpose == "feedback":
            await _handle_feedback(log, caller_phone, db)
        else:
            logger.warning(
                "Unknown agent | agent_id=%s line=%s purpose=%s — no handler",
                agent_id, agent_line, agent_purpose,
            )
    except Exception as exc:
        logger.error(
            "Handler error | call=%s line=%s purpose=%s error=%s",
            payload.id, agent_line, agent_purpose, exc, exc_info=True,
        )
        db.rollback()
        # Re-merge the log row so we don't lose the audit trail on rollback
        _reinsert_log(payload, agent_id, agent_line, agent_purpose, db)
        db.commit()
        return

    # Mark processed AFTER the handler succeeds
    log.processed = 1
    db.commit()


def _reinsert_log(
    payload: BolnaWebhookPayload,
    agent_id: str,
    agent_line: Optional[str],
    agent_purpose: Optional[str],
    db: Session,
) -> None:
    """After a rollback, ensure the log row at least exists (audit trail)."""
    existing = db.query(CallLog).filter(CallLog.bolna_call_id == payload.id).first()
    if existing:
        return
    db.add(CallLog(
        bolna_call_id=payload.id,
        bolna_agent_id=agent_id,
        agent_line=agent_line if agent_line in ("worker", "customer") else None,
        agent_purpose=agent_purpose,
        call_status=payload.status,
        extracted_data=payload.extracted_data,
        events=[payload.model_dump()],
        processed=0,
    ))


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 1 — Arjun (worker inbound)
# Extractions:
#   scenario_completed: new_worker_registered | registration_incomplete |
#                       out_of_scope | idle_callback | job_marked_complete |
#                       deregister_request | unclear
#   worker_name, worker_type, locality, experience_years,
#   job_completion_confirmed (yes/no/not_applicable), additional_notes
# ─────────────────────────────────────────────────────────────────────────────

VALID_WORKER_TYPES = {"electrician", "plumber", "painter", "mason", "locksmith"}


async def _handle_worker_inbound(log: CallLog, caller_phone: str, db: Session) -> None:
    data = log.extracted_data or {}

    # Scenario is the top-level dispatcher within this agent
    scenario = _extract(data, "scenario_completed")
    logger.info("Worker inbound scenario_completed=%s", scenario)

    if scenario == "new_worker_registered":
        _register_worker(data, caller_phone, db)
        return

    if scenario == "job_marked_complete":
        await _worker_marks_job_complete(caller_phone, db)
        return

    if scenario == "deregister_request":
        worker = db.query(Worker).filter(Worker.phone_number == caller_phone).first()
        if worker:
            worker.availability = "unavailable"
            logger.info("Worker %s marked unavailable (deregister)", caller_phone)
        return

    # registration_incomplete, out_of_scope, idle_callback, unclear, or unknown
    logger.info("Worker inbound: no DB mutation needed (scenario=%s)", scenario)


def _register_worker(data: dict, caller_phone: str, db: Session) -> None:
    name = _extract(data, "worker_name")
    worker_type = _extract(data, "worker_type")
    locality = _extract(data, "locality")
    exp_raw = _extract(data, "experience_years")

    # Sanitize worker_type: must be in valid enum; else drop
    if worker_type not in VALID_WORKER_TYPES:
        worker_type = None

    # Parse experience_years as int; default 0
    experience = 0
    if exp_raw:
        try:
            experience = int(float(exp_raw))
        except (ValueError, TypeError):
            experience = 0

    worker = db.query(Worker).filter(Worker.phone_number == caller_phone).first()
    if worker:
        worker.name = name or worker.name
        worker.worker_type = worker_type or worker.worker_type
        worker.locality = locality or worker.locality
        worker.experience_years = experience or worker.experience_years
        worker.updated_at = _utcnow()
        logger.info("Worker updated: %s", caller_phone)
    else:
        db.add(Worker(
            phone_number=caller_phone,
            name=name,
            worker_type=worker_type,
            locality=locality,
            experience_years=experience,
            availability="available",
        ))
        logger.info("Worker registered: %s", caller_phone)


async def _worker_marks_job_complete(caller_phone: str, db: Session) -> None:
    """Worker called inbound to confirm their job is done."""
    worker = db.query(Worker).filter(Worker.phone_number == caller_phone).first()
    if not worker:
        logger.warning("job_marked_complete but worker not found: %s", caller_phone)
        return

    job = (
        db.query(Job)
        .filter(Job.worker_id == worker.id, Job.job_status == "paired_active")
        .first()
    )
    if not job:
        logger.warning("No paired_active job for worker %s", caller_phone)
        return

    job.job_status = "worker_marked_complete"
    worker.availability = "available"
    worker.current_job_id = None
    logger.info("Job %s marked complete by worker %s", job.id, caller_phone)

    # Trigger outbound feedback call to customer
    await _trigger_feedback_call(job, worker, db)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 2 — Arjun Job Offer (worker outbound)
# Extractions:
#   job_offer_decision: accepted | declined | unclear
#   pairing_acknowledged: yes | no | not_applicable
#   additional_notes
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_job_offer(log: CallLog, caller_phone: str, db: Session) -> None:
    data = log.extracted_data or {}
    decision = _extract(data, "job_offer_decision")
    logger.info("Job offer decision=%s (worker=%s)", decision, caller_phone)

    worker = db.query(Worker).filter(Worker.phone_number == caller_phone).first()
    if not worker:
        logger.warning("Job offer callback but worker not found: %s", caller_phone)
        return

    job = (
        db.query(Job)
        .filter(
            Job.offered_worker_id == worker.id,
            Job.job_status == "worker_offered",
        )
        .first()
    )
    if not job:
        logger.warning(
            "No pending 'worker_offered' job for worker %s (might be already resolved)",
            caller_phone,
        )
        return

    if decision == "accepted":
        job.worker_id = worker.id
        job.offered_worker_id = None
        job.job_status = "paired_active"
        job.paired_at = _utcnow()
        worker.availability = "paired"
        worker.current_job_id = job.id
        logger.info("Paired worker %s → job %s", caller_phone, job.id)
        await _trigger_pairing_call(job, worker, db)

    elif decision == "declined" or decision == "unclear":
        # Revert job to searching; add this worker to the declined list
        declined = list(job.declined_worker_ids or [])
        if worker.id not in declined:
            declined.append(worker.id)
        job.declined_worker_ids = declined
        job.offered_worker_id = None
        job.job_status = "searching_worker"
        logger.info(
            "Worker %s %s job %s — back to searching",
            caller_phone, decision, job.id,
        )

    else:
        # No/blank decision — also revert, play safe
        logger.warning(
            "Job offer decision missing for worker %s — reverting job %s",
            caller_phone, job.id,
        )
        declined = list(job.declined_worker_ids or [])
        if worker.id not in declined:
            declined.append(worker.id)
        job.declined_worker_ids = declined
        job.offered_worker_id = None
        job.job_status = "searching_worker"


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 3 — Priya (customer inbound)
# Extractions:
#   scenario_completed: new_job_registered | registration_incomplete |
#                       out_of_scope | status_inquiry | cancel_request |
#                       lost_worker_number | worker_no_show |
#                       job_complete_informed | unclear
#   customer_name, service_type, job_description, locality, additional_notes
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_customer_inbound(log: CallLog, caller_phone: str, db: Session) -> None:
    data = log.extracted_data or {}
    scenario = _extract(data, "scenario_completed")
    logger.info("Customer inbound scenario_completed=%s", scenario)

    if scenario == "new_job_registered":
        _register_new_job(data, caller_phone, db)
        return

    if scenario == "cancel_request":
        _cancel_customer_active_job(caller_phone, db)
        return

    if scenario == "worker_no_show":
        # Log only; flag for manual review. No automatic rematching for demo scope.
        logger.info("Worker no-show reported by customer %s", caller_phone)
        return

    # status_inquiry, lost_worker_number, job_complete_informed,
    # registration_incomplete, out_of_scope, unclear → no DB mutation
    logger.info("Customer inbound: no DB mutation needed (scenario=%s)", scenario)


def _register_new_job(data: dict, caller_phone: str, db: Session) -> None:
    name = _extract(data, "customer_name")
    locality = _extract(data, "locality")
    service_type = _extract(data, "service_type")
    description = _extract(data, "job_description")

    if service_type not in VALID_WORKER_TYPES:
        logger.warning(
            "Customer %s provided invalid service_type '%s' — skipping job creation",
            caller_phone, service_type,
        )
        return

    customer = db.query(Customer).filter(Customer.phone_number == caller_phone).first()
    if customer:
        customer.name = name or customer.name
        customer.locality = locality or customer.locality
        customer.updated_at = _utcnow()
    else:
        customer = Customer(phone_number=caller_phone, name=name, locality=locality)
        db.add(customer)
        db.flush()

    db.add(Job(
        customer_id=customer.id,
        service_type=service_type,
        job_description=description,
        locality=locality or customer.locality,
        job_status="searching_worker",
    ))
    logger.info(
        "Job created | customer=%s type=%s locality=%s",
        caller_phone, service_type, locality,
    )


def _cancel_customer_active_job(caller_phone: str, db: Session) -> None:
    customer = db.query(Customer).filter(Customer.phone_number == caller_phone).first()
    if not customer:
        return
    job = (
        db.query(Job)
        .filter(
            Job.customer_id == customer.id,
            Job.job_status.in_(["searching_worker", "worker_offered", "paired_active"]),
        )
        .order_by(Job.created_at.desc())
        .first()
    )
    if not job:
        return

    # Free any worker currently tied to this job
    if job.offered_worker_id:
        w = db.query(Worker).filter(Worker.id == job.offered_worker_id).first()
        if w:
            w.availability = "available"
            w.current_job_id = None
    if job.worker_id:
        w = db.query(Worker).filter(Worker.id == job.worker_id).first()
        if w:
            w.availability = "available"
            w.current_job_id = None

    job.job_status = "cancelled"
    job.offered_worker_id = None
    logger.info("Job %s cancelled for customer %s", job.id, caller_phone)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 4 — Priya Pairing (customer outbound)
# Extractions:
#   pairing_acknowledged: yes | no | refused
#   additional_notes
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_pairing(log: CallLog, caller_phone: str, db: Session) -> None:
    data = log.extracted_data or {}
    ack = _extract(data, "pairing_acknowledged")
    logger.info("Pairing ack=%s (customer=%s)", ack, caller_phone)

    if ack == "refused":
        # Customer rejected the pairing — cancel the job, free the worker
        customer = db.query(Customer).filter(Customer.phone_number == caller_phone).first()
        if not customer:
            return
        job = (
            db.query(Job)
            .filter(Job.customer_id == customer.id, Job.job_status == "paired_active")
            .order_by(Job.created_at.desc())
            .first()
        )
        if job:
            if job.worker_id:
                w = db.query(Worker).filter(Worker.id == job.worker_id).first()
                if w:
                    w.availability = "available"
                    w.current_job_id = None
            job.job_status = "cancelled"
            job.worker_id = None
            logger.info("Customer %s refused pairing — job %s cancelled", caller_phone, job.id)
        return

    # "yes" or "no" — no DB change; job stays paired_active
    logger.info("Pairing call complete (ack=%s) — no DB change", ack)


# ─────────────────────────────────────────────────────────────────────────────
# AGENT 5 — Priya Feedback (customer outbound)
# Extractions:
#   feedback_rating (numeric 1-10 as string; empty if not given)
#   feedback_comments
#   disputed_completion: yes | no | not_applicable
#   additional_notes
# ─────────────────────────────────────────────────────────────────────────────

async def _handle_feedback(log: CallLog, caller_phone: str, db: Session) -> None:
    data = log.extracted_data or {}
    disputed = _extract(data, "disputed_completion")
    rating_raw = _extract(data, "feedback_rating")
    comments = _extract(data, "feedback_comments")

    customer = db.query(Customer).filter(Customer.phone_number == caller_phone).first()
    if not customer:
        logger.warning("Feedback call but customer not found: %s", caller_phone)
        return

    job = (
        db.query(Job)
        .filter(
            Job.customer_id == customer.id,
            Job.job_status.in_(["worker_marked_complete", "paired_active"]),
        )
        .order_by(Job.created_at.desc())
        .first()
    )
    if not job:
        logger.warning(
            "Feedback call but no worker_marked_complete/paired job for %s",
            caller_phone,
        )
        return

    if disputed == "yes":
        # Customer denied the job is complete — revert
        job.job_status = "paired_active"
        if job.worker_id:
            worker = db.query(Worker).filter(Worker.id == job.worker_id).first()
            if worker:
                worker.availability = "paired"
                worker.current_job_id = job.id
        logger.info("Customer %s disputed completion — job %s back to paired_active", caller_phone, job.id)
        return

    # Parse rating
    rating = None
    if rating_raw:
        try:
            r = float(rating_raw)
            if 1.0 <= r <= 10.0:
                rating = r
        except (ValueError, TypeError):
            pass

    job.feedback_rating = rating
    job.feedback_comments = comments
    job.job_status = "completed"
    job.completed_at = _utcnow()
    logger.info("Job %s completed | rating=%s", job.id, rating)


# ─────────────────────────────────────────────────────────────────────────────
# Outbound call triggers
# ─────────────────────────────────────────────────────────────────────────────

async def _trigger_pairing_call(job: Job, worker: Worker, db: Session) -> None:
    """Tell the customer a worker accepted — share the worker's number."""
    from app.services.bolna_client import trigger_outbound_call

    customer = db.query(Customer).filter(Customer.id == job.customer_id).first()
    if not customer:
        return

    try:
        await trigger_outbound_call(
            line="customer",
            purpose="pairing",
            recipient_phone=customer.phone_number,
            user_data={
                "customer_name": customer.name or "",
                "customer_locality": customer.locality or "",
                "service_type": job.service_type or "",
                "job_description": job.job_description or "",
                "worker_name": worker.name or "",
                "worker_phone": worker.phone_number or "",
                "worker_type": worker.worker_type or "",
            },
        )
    except Exception as exc:
        logger.error("Failed to trigger pairing call for customer %s: %s", customer.phone_number, exc)


async def _trigger_feedback_call(job: Job, worker: Worker, db: Session) -> None:
    """Call customer to collect rating after worker marked complete."""
    from app.services.bolna_client import trigger_outbound_call

    customer = db.query(Customer).filter(Customer.id == job.customer_id).first()
    if not customer:
        return

    try:
        await trigger_outbound_call(
            line="customer",
            purpose="feedback",
            recipient_phone=customer.phone_number,
            user_data={
                "customer_name": customer.name or "",
                "customer_locality": customer.locality or "",
                "service_type": job.service_type or "",
                "worker_name": worker.name or "",
                "worker_type": worker.worker_type or "",
            },
        )
    except Exception as exc:
        logger.error("Failed to trigger feedback call for customer %s: %s", customer.phone_number, exc)
