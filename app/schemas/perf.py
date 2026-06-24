from pydantic import BaseModel, ConfigDict

class PerfTaskCreate(BaseModel):
    name: str
    target_host: str
    target_path: str
    users: int
    spawn_rate: int
    duration: int


class PerfTaskOut(PerfTaskCreate):
    id: int
    status: str
    rps: float | None = None
    avg_response_ms: float | None = None
    fail_ratio: float | None = None
    model_config = ConfigDict(from_attributes=True)



