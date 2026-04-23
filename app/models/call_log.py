from datetime import datetime, timezone

from sqlalchemy import TIMESTAMP, Column, Enum, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB

from app.db.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CallLog(Base):
    """
    ONE row per call (unique on bolna_call_id).

    Bolna sends multiple webhook events for the same call (e.g. intermediate
    status, then final 'completed' with extracted_data). We upsert into the
    same row, merging in only the fields that are present in each event.
    Raw webhook payloads are appended to `events` as an audit trail.
    """

    __tablename__ = "call_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    bolna_call_id = Column(String(100), nullable=False, unique=True, index=True)
    bolna_agent_id = Column(String(100))

    agent_line = Column(
        Enum("worker", "customer", name="agent_line_enum"), nullable=True
    )
    agent_purpose = Column(String(30))  # inbound | job_offer | pairing | feedback
    direction = Column(
        Enum("inbound", "outbound", name="call_direction_enum"), nullable=True
    )

    caller_phone = Column(String(20))
    agent_phone = Column(String(20))

    call_status = Column(String(30))            # latest status observed
    smart_status = Column(String(30))
    hangup_reason = Column(String(80))
    conversation_duration = Column(Numeric(8, 2))
    transcript = Column(Text)
    extracted_data = Column(JSONB, nullable=True)

    # Processing state — idempotency flag
    processed = Column(Integer, default=0, nullable=False)  # 0 = not yet, 1 = done

    # Audit trail: list of all webhook events we saw for this call
    events = Column(JSONB, default=list)

    first_seen_at = Column(TIMESTAMP(timezone=True), default=_utcnow)
    last_updated_at = Column(TIMESTAMP(timezone=True), default=_utcnow, onupdate=_utcnow)

    def __repr__(self) -> str:
        return f"<CallLog {self.bolna_call_id} status={self.call_status} processed={self.processed}>"
