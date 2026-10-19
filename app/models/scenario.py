from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Scenario(Base):
    __tablename__ = "scenario"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    # 有序来源 ID 的兼容投影；保留重复和失效引用，不作为副本的执行配置。
    case_ids = Column(JSON, nullable=False)
    # Each occurrence has its own request/assertion snapshot; case_ids is a
    # compatibility projection of source_case_id, never the execution source.
    steps = Column(JSON, nullable=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
