from datetime import datetime
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from app.schemas.base import NamedSchema
from app.schemas.perf_plan import PerfLoadConfig

class PerfTaskCreate(NamedSchema):
    target_host: str = Field(min_length=1, max_length=255)
    target_path: str = Field(min_length=1, max_length=255)
    users: int = Field(ge=1, le=100000)
    spawn_rate: int = Field(ge=1, le=100000)
    duration: int = Field(ge=1, le=86400)
    load_config: PerfLoadConfig | None = None

    @field_validator("target_host")
    @classmethod
    def validate_target_host(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("目标 Host 必须以 http:// 或 https:// 开头")
        parsed = urlsplit(value)
        if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("目标 Host 必须包含主机名，不能包含凭证、查询参数或片段")
        return value

    @field_validator("target_path")
    @classmethod
    def normalize_target_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("目标路径不能为空")
        return value if value.startswith("/") else "/" + value

class PerfTaskOut(PerfTaskCreate):
    id: int
    status: str
    celery_task_id: str | None = None
    queued_at: datetime | None = None
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    finished_at: datetime | None = None
    failure_reason: str | None = None
    rps: float | None = None
    avg_response_ms: float | None = None
    p95_response_ms: float | None = None
    p99_response_ms: float | None = None
    request_stats: list | None = None
    error_summary: list | None = None
    history_samples: list | None = None
    iteration_stats: dict | None = None
    fail_ratio: float | None = None
    latest_run_id: int | None = None
    history_count: int = 0
    model_config = ConfigDict(from_attributes=True)


class PerfRunOut(BaseModel):
    id: int
    task_id: int
    status: str
    created_at: datetime
    result: PerfTaskOut


class PerfRunClear(BaseModel):
    run_ids: list[int] = Field(default_factory=list, max_length=200)
    all_finished: bool = False

    @model_validator(mode="after")
    def validate_selection(self):
        if self.all_finished == bool(self.run_ids):
            raise ValueError("请选择执行记录或清理全部已结束记录")
        if any(value < 1 for value in self.run_ids) or len(set(self.run_ids)) != len(self.run_ids):
            raise ValueError("执行记录ID必须为不重复的正整数")
        return self
