from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from app.database import Base


class TrafficCapture(Base):
    """One durable switch per user/project; switching pages does not stop it."""
    __tablename__ = "traffic_capture"
    project_id = Column(Integer, ForeignKey("project.id", ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    capture_id = Column(String(36), nullable=False)
    started_at = Column(DateTime, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    stopped_at = Column(DateTime, nullable=True)
