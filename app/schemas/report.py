from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ReportOut(BaseModel):
    id: int
    case_id: int
    case_name: str | None = None
    passed: bool
    detail: dict | list | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ReportPage(BaseModel):
    items: list[ReportOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    passed_count: int
    failed_count: int
    pass_rate: float


class ScenarioReportStepOut(BaseModel):
    id: int
    sequence: int
    case_id: int
    case_name: str | None = None
    passed: bool
    request_detail: dict | None = None
    response_detail: dict | None = None
    assertions: list | None = None
    extracted_variables: dict | None = None
    error: str | None = None
    duration_ms: int
    model_config = ConfigDict(from_attributes=True)


class ScenarioReportOut(BaseModel):
    id: int
    scenario_id: int
    scenario_name: str
    passed: bool
    total_steps: int
    passed_steps: int
    failed_steps: int
    duration_ms: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


class ScenarioReportDetail(ScenarioReportOut):
    steps: list[ScenarioReportStepOut]


class ScenarioReportPage(BaseModel):
    items: list[ScenarioReportOut]
    total: int
    page: int
    page_size: int
    total_pages: int
    passed_count: int
    failed_count: int
    pass_rate: float




