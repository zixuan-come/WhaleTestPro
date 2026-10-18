from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, JSON, String
from app.database import Base


class ExecutionReport(Base):
    __tablename__ = "execution_report"
    __table_args__ = (Index("ix_execution_report_project_kind_parent", "project_id", "kind", "parent_id"),)

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    # Historical snapshots intentionally survive deletion of their source objects.
    parent_id = Column(Integer, nullable=True, index=True)
    kind = Column(String(20), nullable=False)
    object_id = Column(Integer, nullable=True)
    name = Column(String(100), nullable=False)
    passed = Column(Boolean, nullable=True)
    status = Column(String(20), nullable=False, default="running")
    trigger_source = Column(String(20), nullable=False, default="manual")
    environment_name = Column(String(100), nullable=True)
    created_at = Column(DateTime, nullable=False)
    duration_ms = Column(Integer, nullable=True)
    detail = Column(JSON, nullable=True)
