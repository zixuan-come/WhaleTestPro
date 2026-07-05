from sqlalchemy import Column, Integer, String, JSON, ForeignKey, DateTime
from sqlalchemy.sql import func
from app.database import Base


class Scenario(Base):
    __tablename__ = "scenario"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    description = Column(String(500), nullable=True)
    # 有序的 case id 数组,存 JSON。DB 层不做 FK 校验(方便重排/丢弃孤立引用),前端渲染时按 id 找 case
    case_ids = Column(JSON, nullable=False)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
