from sqlalchemy import Column, Integer, String, JSON, DateTime, func
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
