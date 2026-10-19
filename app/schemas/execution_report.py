from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field

ReportKind = Literal["case", "scenario", "suite", "regression"]


class ExecutionReportItem(BaseModel):
    id: str
    kind: ReportKind
    name: str
    passed: bool | None
    status: str
    trigger_source: str | None
    environment_name: str | None
    duration_ms: int | None
    created_at: datetime
    historical: bool
    folder_id: int | None = None


class ExecutionReportDetail(ExecutionReportItem):
    detail: dict | list | None
    children: list[ExecutionReportItem] = Field(default_factory=list)


class ExecutionReportPage(BaseModel):
    items: list[ExecutionReportItem]
    total: int
    page: int
    page_size: int
    total_pages: int
    passed_count: int
    failed_count: int
    running_count: int
    pass_rate: float
