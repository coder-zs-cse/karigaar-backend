"""
Job queue background poller.

Polls every JOB_POLL_INTERVAL_SECONDS for 'searching_worker' jobs.
For each job it finds an available worker that matches service_type +
locality and has NOT previously declined this job, then triggers an
outbound job-offer call via Agent 2 (Arjun — Job Offer).

Worker acceptance/decline comes back through the webhook processor,
which updates the job status accordingly.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import settings
from app.db.database import SessionLocal
from app.models import Customer, Job, Worker
from app.services.bolna_client import trigger_outbound_call

logger = logging.getLogger(__name__)

_running = False


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _match_and_reserve_sync(job_id: int) -> dict | None:
    """
    Atomic sync DB work: find a worker for the given job, reserve it
    (set status='worker_offered' + offered_worker_id), and return the
    data needed to make the outbound call.

    Returns None if the job is no longer 'searching_worker' or no worker found.
    """
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if not job or job.job_status != "searching_worker":
            return None

        declined_ids = list(job.declined_worker_ids or [])

        # Primary filter: type + locality + available + not previously declined
        query = db.query(Worker).filter(
            Worker.worker_type == job.service_type,
            Worker.availability == "available",
        )
        if declined_ids:
            query = query.filter(Worker.id.notin_(declined_ids))
        if job.locality:
            query = query.filter(Worker.locality.ilike(f"%{job.locality}%"))

        worker = query.first()

        if not worker:
            # Fallback: drop locality constraint
            query = db.query(Worker).filter(
                Worker.worker_type == job.service_type,
                Worker.availability == "available",
            )
            if declined_ids:
                query = query.filter(Worker.id.notin_(declined_ids))
            worker = query.first()

        if not worker:
            logger.info(
                "No available worker | job=%s type=%s locality=%s declined=%s",
                job.id, job.service_type, job.locality, declined_ids,
            )
            return None

        # Reserve
        job.job_status = "worker_offered"
        job.offered_worker_id = worker.id
        job.updated_at = _utcnow()
        db.commit()

        customer = db.query(Customer).filter(Customer.id == job.customer_id).first()

        return {
            "job_id": job.id,
            "worker_phone": worker.phone_number,
            "worker_name": worker.name or "",
            "worker_type": worker.worker_type or "",
            "worker_locality": worker.locality or "",
            "service_type": job.service_type or "",
            "job_description": job.job_description or "",
            "job_locality": job.locality or "",
            "customer_name": customer.name if customer else "",
            "customer_phone": customer.phone_number if customer else "",
        }


def _revert_job_sync(job_id: int) -> None:
    """Undo the reservation if the Bolna call failed."""
    with SessionLocal() as db:
        job = db.query(Job).filter(Job.id == job_id).first()
        if job and job.job_status == "worker_offered":
            job.job_status = "searching_worker"
            job.offered_worker_id = None
            db.commit()


def _get_searching_job_ids() -> list[int]:
    with SessionLocal() as db:
        rows = db.query(Job.id).filter(Job.job_status == "searching_worker").all()
        return [r.id for r in rows]


async def _poll_once() -> None:
    try:
        job_ids = await asyncio.to_thread(_get_searching_job_ids)
        if not job_ids:
            return

        logger.info("Job queue: %d searching_worker job(s)", len(job_ids))

        for job_id in job_ids:
            call_data = await asyncio.to_thread(_match_and_reserve_sync, job_id)
            if not call_data:
                continue

            try:
                await trigger_outbound_call(
                    line="worker",
                    purpose="job_offer",
                    recipient_phone=call_data["worker_phone"],
                    user_data={
                        "worker_name": call_data["worker_name"],
                        "worker_type": call_data["worker_type"],
                        "worker_locality": call_data["worker_locality"],
                        "service_type": call_data["service_type"],
                        "job_description": call_data["job_description"],
                        "job_locality": call_data["job_locality"],
                        "customer_name": call_data["customer_name"],
                        "customer_phone": call_data["customer_phone"],
                    },
                )
                logger.info(
                    "Outbound job_offer queued | worker=%s job=%s",
                    call_data["worker_phone"], call_data["job_id"],
                )
            except Exception as exc:
                logger.error(
                    "Bolna job_offer call failed for worker %s: %s — reverting job %s",
                    call_data["worker_phone"], exc, call_data["job_id"],
                )
                await asyncio.to_thread(_revert_job_sync, call_data["job_id"])

    except Exception as exc:
        logger.error("Job queue poll error: %s", exc, exc_info=True)


async def run_job_queue() -> None:
    global _running
    if _running:
        logger.warning("Job queue already running")
        return
    _running = True

    interval = settings.job_poll_interval_seconds
    logger.info("Job queue started | interval=%ds", interval)

    while True:
        try:
            await _poll_once()
        except Exception as exc:
            logger.error("Unexpected error: %s", exc, exc_info=True)
        await asyncio.sleep(interval)
