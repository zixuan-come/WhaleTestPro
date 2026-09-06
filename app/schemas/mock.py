from pydantic import ConfigDict, Field, field_validator
from app.schemas.base import NamedSchema

class MockCreate(NamedSchema):
    path: str = Field(min_length=1, max_length=255)
    method: str = Field(min_length=1, max_length=10)
    status: int = Field(default=200, ge=100, le=599)
    body: dict | None = None
    delay_ms: int = Field(default=0, ge=0, le=60000)

    @field_validator("path")
    @classmethod
    def normalize_path(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("匹配路径不能为空")
        value = value if value.startswith("/") else "/" + value
        if len(value) > 255:
            raise ValueError("匹配路径长度不能超过 255 个字符")
        return value

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("请求方法不能为空")
        return value

class MockOut(MockCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)
