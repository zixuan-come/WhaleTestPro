from pydantic import BaseModel, ConfigDict, Field, field_validator
from app.schemas.base import NamedSchema


class InterfaceCreate(NamedSchema):
    method: str
    url: str
    headers: dict | None = None
    params: dict | None = None
    body: dict | None = None
    category: str | None = Field(default=None, max_length=50)

    @field_validator("method")
    @classmethod
    def validate_method(cls, value: str) -> str:
        value = value.strip().upper()
        if value not in {"GET", "POST", "PUT", "DELETE", "PATCH"}:
            raise ValueError("请求方法必须是 GET、POST、PUT、DELETE 或 PATCH")
        return value

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("请求 URL 不能为空")
        if len(value) > 500:
            raise ValueError("请求 URL 长度不能超过 500 个字符")
        if not value.startswith("/"):
            raise ValueError("请求 URL 必须以 / 开头")
        return value

    @field_validator("category")
    @classmethod
    def normalize_category(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        return value or None


class InterfaceOut(InterfaceCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CategoryRename(BaseModel):
    old_name: str
    new_name: str


class InterfaceMigrate(BaseModel):
    target_interface_id: int