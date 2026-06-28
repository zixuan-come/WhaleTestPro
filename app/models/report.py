from sqlalchemy import Column, Integer, Boolean, JSON, DateTime, func
from app.database import Base

class TestReport(Base):
    __tablename__ = "test_report"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    detail = Column(JSON, nullable=True)
    created_at = Column(DateTime, server_default=func.now())







