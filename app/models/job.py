from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, Column, Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


JobStatusEnum = Enum(
    "searching_worker",       # customer posted, no worker yet
    "worker_offered",         # outbound call placed to worker, awaiting response
    "paired_active",          # worker accepted, both parties have each other's number
    "worker_marked_complete", # worker said done, awaiting customer confirmation
    "completed",              # customer confirmed + feedback collected
    "cancelled",
    name="job_status_enum",
)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)

    # Set once worker accepts
    worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)

    # Temporary: worker currently being called (offer in flight)
    offered_worker_id = Column(Integer, ForeignKey("workers.id"), nullable=True)

    # Workers who already declined this job — so we don't call them again
    declined_worker_ids = Column(JSONB, default=list)

    service_type = Column(
        Enum("electrician", "plumber", "painter", "mason", "locksmith",
             name="service_type_enum"),
        nullable=False,
    )
    job_description = Column(Text)
    locality = Column(String(100))
    job_status = Column(JobStatusEnum, default="searching_worker", nullable=False)

    feedback_rating = Column(Numeric(3, 1))   # 1.0 – 10.0
    feedback_comments = Column(Text)

    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    paired_at = Column(TIMESTAMP(timezone=True), nullable=True)
    completed_at = Column(TIMESTAMP(timezone=True), nullable=True)
    updated_at = Column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Job {self.id} {self.service_type} {self.job_status}>"
