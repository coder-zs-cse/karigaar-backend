"""
Caller context service.

Serves pre-call context for the TWO inbound agents:
  - Agent 1 (Arjun / worker inbound)
  - Agent 3 (Priya / customer inbound)

Outbound agents do not use caller-context — their user_data is passed
directly in the POST /call request by our backend.
"""

import logging

from sqlalchemy.orm import Session

from app.models import Customer, Job, Worker
from app.schemas.context import CustomerInboundContext, WorkerInboundContext

logger = logging.getLogger(__name__)


def get_worker_inbound_context(
    phone_number: str, db: Session
) -> WorkerInboundContext:
    """Resolve state for a worker calling the worker inbound line."""

    worker = db.query(Worker).filter(Worker.phone_number == phone_number).first()

    if not worker:
        logger.info("Worker context: NEW | phone=%s", phone_number)
        return WorkerInboundContext(scenario="new_worker")

    # Paired on an active job → show pairing context
    if worker.availability == "paired" and worker.current_job_id:
        job = db.query(Job).filter(Job.id == worker.current_job_id).first()
        if job and job.job_status in ("paired_active", "worker_marked_complete"):
            customer = db.query(Customer).filter(Customer.id == job.customer_id).first()
            logger.info(
                "Worker context: PAIRED_IN_PROGRESS | phone=%s job=%s",
                phone_number, job.id,
            )
            return WorkerInboundContext(
                scenario="paired_in_progress",
                worker_name=worker.name or "",
                worker_type=worker.worker_type or "",
                worker_locality=worker.locality or "",
                customer_phone=customer.phone_number if customer else "",
                customer_name=customer.name if customer else "",
                service_type=job.service_type or "",
                job_description=job.job_description or "",
                job_locality=job.locality or "",
            )

    logger.info("Worker context: REGISTERED_IDLE | phone=%s", phone_number)
    return WorkerInboundContext(
        scenario="registered_idle",
        worker_name=worker.name or "",
        worker_type=worker.worker_type or "",
        worker_locality=worker.locality or "",
    )


def get_customer_inbound_context(
    phone_number: str, db: Session
) -> CustomerInboundContext:
    """Resolve state for a customer calling the customer inbound line."""

    customer = db.query(Customer).filter(Customer.phone_number == phone_number).first()

    if not customer:
        logger.info("Customer context: NEW | phone=%s", phone_number)
        return CustomerInboundContext(scenario="new_customer")

    # Find most recent active job (if any)
    job = (
        db.query(Job)
        .filter(
            Job.customer_id == customer.id,
            Job.job_status.in_([
                "searching_worker",
                "worker_offered",
                "paired_active",
                "worker_marked_complete",
            ]),
        )
        .order_by(Job.created_at.desc())
        .first()
    )

    if not job:
        # Returning customer with no active job — treat as "new request" flow
        logger.info("Customer context: RETURNING_NO_ACTIVE | phone=%s", phone_number)
        return CustomerInboundContext(
            scenario="new_customer",
            customer_name=customer.name or "",
            customer_locality=customer.locality or "",
        )

    worker = None
    if job.worker_id:
        worker = db.query(Worker).filter(Worker.id == job.worker_id).first()

    base = dict(
        customer_name=customer.name or "",
        customer_locality=customer.locality or "",
        service_type=job.service_type or "",
        job_description=job.job_description or "",
        worker_name=worker.name if worker else "",
        worker_phone=worker.phone_number if worker else "",
        worker_type=worker.worker_type if worker else "",
    )

    if job.job_status in ("searching_worker", "worker_offered"):
        logger.info("Customer context: SEARCHING_WORKER | phone=%s job=%s", phone_number, job.id)
        return CustomerInboundContext(scenario="searching_worker", **base)

    if job.job_status in ("paired_active", "worker_marked_complete"):
        logger.info("Customer context: PAIRED_IN_PROGRESS | phone=%s job=%s", phone_number, job.id)
        return CustomerInboundContext(scenario="paired_in_progress", **base)

    # Fallback
    return CustomerInboundContext(
        scenario="new_customer",
        customer_name=customer.name or "",
        customer_locality=customer.locality or "",
    )
