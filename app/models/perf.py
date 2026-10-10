from sqlalchemy import Column, DateTime, Integer, String, Float, ForeignKey, JSON
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
    celery_task_id = Column(String(255), nullable=True, index=True)
    queued_at = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True, index=True)
    finished_at = Column(DateTime, nullable=True)
    failure_reason = Column(String(500), nullable=True)
    rps = Column(Float, nullable=True)
    avg_response_ms = Column(Float, nullable=True)
    p95_response_ms = Column(Float, nullable=True)
    p99_response_ms = Column(Float, nullable=True)
    request_stats = Column(JSON, nullable=True)
    error_summary = Column(JSON, nullable=True)
    history_samples = Column(JSON, nullable=True)
    fail_ratio = Column(Float, nullable=True)
    project_id = Column(Integer, ForeignKey("project.id"), nullable=False)



