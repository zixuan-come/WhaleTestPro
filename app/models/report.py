from sqlalchemy import Column, Integer, Boolean, JSON, DateTime, String, func, ForeignKey
from app.database import Base

class TestReport(Base):
    __tablename__ = "test_report"
    id = Column(Integer, primary_key=True, index=True)
    case_id = Column(Integer, nullable=False)
    passed = Column(Boolean, nullable=False)
    detail = Column(JSON, nullable=True)
    suite_id = Column(Integer, ForeignKey("test_suite.id"), nullable=True)
    suite_name = Column(String(100), nullable=True)
    execution_type = Column(String(20), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)







