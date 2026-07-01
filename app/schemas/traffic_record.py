from datetime import datetime
from pydantic import BaseModel, ConfigDict


class TrafficRecordCreate(BaseModel):
    method: str
    path: str
    request_headers: dict | None = None
    request_body: dict | None = None
    response_status: int | None = None
    response_body: dict | None = None


class TrafficRecordOut(TrafficRecordCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
