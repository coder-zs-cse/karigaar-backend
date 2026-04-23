from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, Column, Integer, String

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    phone_number = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(100))
    locality = Column(String(100))
    created_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    updated_at = Column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<Customer {self.phone_number} {self.name}>"
