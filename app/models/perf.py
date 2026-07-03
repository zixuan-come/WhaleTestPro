from sqlalchemy import Column, Integer, String, Float, ForeignKey
from app.database import Base


class PerfTask(Base):
    __tablename__ = "perf_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    target_host = Column(String(255), nullable=False)
    target_path = Column(String(255), nullable=False)
    users = Column(Integer, nullable=False)
    spawn_rate = Column(Integer, nullable=False)
    duration = Column(Integer, nullable=False)
    status = Column(String(50), nullable=False, default="pending")
    rps = Column(Float, nullable=True)
    avg_response_ms = Column(Float, nullable=True)
    fail_ratio = Column(Float, nullable=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)



