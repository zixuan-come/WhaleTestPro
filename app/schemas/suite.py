from pydantic import BaseModel, Field, field_validator
from typing import Literal
from datetime import datetime


class SuiteCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    type: Literal["scenario", "case", "mixed"]
    scenario_ids: list[int] | None = None
    case_ids: list[int] | None = None
    tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("套件名称不能为空或纯空格")
        return stripped

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None:
            return value.strip() or None
        return None

    @field_validator("scenario_ids", "case_ids")
    @classmethod
    def validate_ids(cls, value: list[int] | None) -> list[int] | None:
        if value is not None and len(value) > 100:
            raise ValueError("单个套件最多包含 100 个场景或用例")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        if value is not None:
            if len(value) > 20:
                raise ValueError("单个套件最多包含 20 个标签")
            for tag in value:
                if not tag.strip():
                    raise ValueError("标签不能为空")
        return value


class SuiteUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = Field(None, max_length=500)
    type: Literal["scenario", "case", "mixed"] | None = None
    scenario_ids: list[int] | None = None
    case_ids: list[int] | None = None
    tags: list[str] | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            stripped = value.strip()
            if not stripped:
                raise ValueError("套件名称不能为空或纯空格")
            return stripped
        return None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        if value is not None:
            return value.strip() or None
        return None


class SuiteOut(BaseModel):
    id: int
    name: str
    description: str | None
    project_id: int
    type: str
    scenario_ids: list[int] | None
    case_ids: list[int] | None
    tags: list[str] | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
