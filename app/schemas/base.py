from pydantic import BaseModel, field_validator


class NamedSchema(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("名称不能为空")
        if len(value) > 100:
            raise ValueError("名称长度不能超过 100 个字符")
        return value
