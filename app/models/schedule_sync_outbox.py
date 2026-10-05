from sqlalchemy import Column, DateTime, Integer, JSON, String, func

from app.database import Base


class ScheduleSyncOutbox(Base):
    """Persistent, idempotent request to synchronize MySQL with RedBeat."""

    __tablename__ = "schedule_sync_outbox"

    # One latest event per schedule. A later update/delete replaces stale work.
    schedule_id = Column(Integer, primary_key=True)
    action = Column(String(20), nullable=False)
    payload = Column(JSON, nullable=True)
    attempts = Column(Integer, nullable=False, default=0, server_default="0")
    last_error = Column(String(500), nullable=True)
    updated_at = Column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
