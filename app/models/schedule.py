from sqlalchemy import Column, Integer, String, Boolean, ForeignKey
from app.database import Base


class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cron = Column(String(100), nullable=False)
    tag = Column(String(50), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)











