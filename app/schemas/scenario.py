from datetime import datetime
import json
from uuid import uuid4
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.schemas.base import NamedSchema
from app.schemas.request_config import PathParameterValues


class ScenarioStep(BaseModel):
    model_config = ConfigDict(extra='forbid')
    step_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=64)
    source_case_id: int
    source_case_name: str | None = Field(default=None, max_length=100)
    interface_id: int | None = Field(default=None, gt=0)
    interface_name: str | None = Field(default=None, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    method: Literal['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS'] | None = None
    url: str | None = Field(default=None, max_length=500)
    path_params: PathParameterValues | None = None
    headers: dict | None = None
    params: dict | None = None
    body: dict | None = None
    expected_status: int = Field(default=200, ge=100, le=599)
    assertions: list[dict] | None = None
    extract_rules: dict[str, str] | None = None
    # Retain legacy metadata. Chain execution still excludes SQL/datasets/retry,
    # and load-plan import must continue to reject unsupported configurations.
    setup_sql: list | None = None
    teardown_sql: list | None = None
    datasets: list | None = None
    retries: int = Field(default=0, ge=0)
    missing_reason: str | None = Field(default=None, max_length=200)

    @model_validator(mode='after')
    def valid_request(self):
        self.step_id = self.step_id.strip()
        if not self.step_id:
            raise ValueError('步骤标识不能为空')
        self.name = self.name.strip()
        if not self.name:
            raise ValueError('步骤名称不能为空')
        if not self.missing_reason and (self.interface_id is None or not self.method or not self.url or not self.url.startswith('/')):
            raise ValueError('步骤必须关联接口，并填写请求方法和相对路径')
        if not self.missing_reason and self.source_case_id <= 0:
            raise ValueError('步骤来源用例 ID 必须大于 0')
        return self


class ScenarioCreate(NamedSchema):
    description: str | None = Field(default=None, max_length=500)
    case_ids: list[int] = []
    steps: list[ScenarioStep] | None = Field(default=None, max_length=1000)

    @model_validator(mode='after')
    def valid_steps(self):
        if self.steps is not None:
            keys = [step.step_id for step in self.steps]
            if len(keys) != len(set(keys)):
                raise ValueError('场景内步骤标识不能重复')
            if len(json.dumps([step.model_dump() for step in self.steps], ensure_ascii=False).encode()) > 2 * 1024 * 1024:
                raise ValueError('场景步骤配置不能超过 2 MiB')
        return self


class ScenarioOut(ScenarioCreate):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
