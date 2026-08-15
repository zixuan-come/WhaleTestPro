from pydantic import ConfigDict, Field
from app.schemas.base import NamedSchema

class PerfTaskCreate(NamedSchema):
    target_host: str
    target_path: str
    users: int = Field(ge=1)
    spawn_rate: int = Field(ge=1)
    duration: int = Field(ge=1)


class PerfTaskOut(PerfTaskCreate):
    id: int
    status: str
    rps: float | None = None
    avg_response_ms: float | None = None
    fail_ratio: float | None = None
    model_config = ConfigDict(from_attributes=True)



