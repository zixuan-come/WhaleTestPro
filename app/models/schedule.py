from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, JSON
from app.database import Base


class Schedule(Base):
    __tablename__ = "schedule"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    cron = Column(String(100), nullable=False)
    suite_id = Column(Integer, ForeignKey("test_suite.id"), nullable=True)
    env_id = Column(Integer, ForeignKey("environment.id", ondelete="RESTRICT"), nullable=True)
    enabled = Column(Boolean, nullable=False, default=True)
    selection = Column(JSON, nullable=True)
    notify = Column(Boolean, nullable=False, default=False, server_default="0")
    sync_status = Column(
        String(20),
        nullable=False,
        default="pending",
        server_default="pending",
    )
    sync_error = Column(String(500), nullable=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)











