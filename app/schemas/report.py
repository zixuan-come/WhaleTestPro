from datetime import datetime
from pydantic import BaseModel, ConfigDict

class ReportOut(BaseModel):
    id: int
    case_id: int
    passed: bool
    detail: dict | list | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)




