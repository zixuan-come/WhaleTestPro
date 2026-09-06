from pydantic import ConfigDict, Field, field_validator
from app.schemas.base import NamedSchema

class PerfTaskCreate(NamedSchema):
    target_host: str = Field(min_length=1, max_length=255)
    target_path: str = Field(min_length=1, max_length=255)
    users: int = Field(ge=1, le=100000)
    spawn_rate: int = Field(ge=1, le=100000)
    duration: int = Field(ge=1, le=86400)

    @field_validator("target_host")
    @classmethod
    def validate_target_host(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value.startswith(("http://", "https://")):
            raise ValueError("目标 Host 必须以 http:// 或 https:// 开头")
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
    rps: float | None = None
    avg_response_ms: float | None = None
    fail_ratio: float | None = None
    model_config = ConfigDict(from_attributes=True)
