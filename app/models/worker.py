from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, Column, Enum, ForeignKey, Integer, String

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


WorkerTypeEnum = Enum(
    "electrician", "plumber", "painter", "mason", "locksmith",
    name="worker_type_enum",
)

WorkerAvailabilityEnum = Enum(
    "available", "paired", "unavailable",
    name="worker_availability_enum",
)


class Worker(Base):
    __tablename__ = "workers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100))
    worker_type = Column(WorkerTypeEnum)
    locality = Column(String(100))
    experience_years = Column(Integer, default=0)
    availability = Column(WorkerAvailabilityEnum, default="available", nullable=False)

    # FK set after job is confirmed (avoid circular FK at creation time)
    current_job_id = Column(
        Integer,
        ForeignKey("jobs.id", use_alter=True, name="fk_worker_current_job"),
        nullable=True,
    )

    registered_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Worker {self.phone_number} {self.worker_type} {self.locality}>"
