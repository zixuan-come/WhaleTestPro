from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class TrafficRecordCreate(BaseModel):
    method: str
    path: str
    request_headers: dict | None = None
    request_body: Any = None
    response_status: int | None = None
    response_body: Any = None
    # 由 recording_middleware 塞进来,不是 API 请求参数:见 main.py _extract_project_id
    project_id: int
    source: str | None = None
    capture_id: str | None = None
    interface_name: str | None = None
    request_params: dict | None = None
    target_host: str | None = None
    duration_ms: int | None = None


class TrafficRecordOut(TrafficRecordCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

