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




