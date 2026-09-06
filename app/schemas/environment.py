from pydantic import ConfigDict, Field, field_validator
from app.schemas.base import NamedSchema



class EnvironmentCreate(NamedSchema):
    base_url: str = Field(min_length=1, max_length=500)
    variables: dict | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        value = value.strip().rstrip("/")
        if not value:
            raise ValueError("Base URL 不能为空")
        if not value.startswith(("http://", "https://")):
            raise ValueError("Base URL 必须以 http:// 或 https:// 开头")
        return value



class EnvironmentOut(EnvironmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
