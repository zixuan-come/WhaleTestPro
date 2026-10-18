from sqlalchemy import Column, Integer, String, JSON, DateTime, func, ForeignKey
from app.database import Base


class TrafficRecord(Base):
    __tablename__ = "traffic_records"

    id = Column(Integer, primary_key=True, index=True)
    method = Column(String(10), nullable=False)
    path = Column(String(500), nullable=False, index=True)
    request_headers = Column(JSON, nullable=True)
    request_body = Column(JSON, nullable=True)
    response_status = Column(Integer, nullable=True)
    response_body = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    source = Column(String(20), nullable=True)  # NULL: historical incoming record
    capture_id = Column(String(36), nullable=True, index=True)
    interface_name = Column(String(200), nullable=True)
    request_params = Column(JSON, nullable=True)
    target_host = Column(String(500), nullable=True)
    duration_ms = Column(Integer, nullable=True)
