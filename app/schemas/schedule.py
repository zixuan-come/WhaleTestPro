from pydantic import ConfigDict, Field, field_validator, model_validator
from celery.schedules import crontab
from app.schemas.base import NamedSchema
from app.schemas.regression import RegressionTargets

class ScheduleCreate(NamedSchema):
    cron: str = Field(min_length=1, max_length=100)
    suite_id: int | None = None
    env_id: int = Field(gt=0)
    enabled: bool = True
    selection: RegressionTargets | None = None
    notify: bool = False

    @model_validator(mode="after")
    def exclusive_selection(self):
        if self.selection is not None and self.suite_id is not None:
            raise ValueError("显式选择测试内容后不能同时配置单套件筛选")
        return self

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        value = value.strip()
        fields = value.split()
        if len(fields) != 5:
            raise ValueError("Cron 必须包含 5 个字段")
        try:
            crontab(minute=fields[0], hour=fields[1], day_of_month=fields[2], month_of_year=fields[3], day_of_week=fields[4])
        except (TypeError, ValueError) as exc:
            raise ValueError("Cron 表达式不合法") from exc
        return value

    @model_validator(mode="before")
    @classmethod
    def reject_retired_tag(cls, value):
        if isinstance(value, dict) and "tag" in value:
            raise ValueError("标签功能已移除，请明确选择测试内容")
        return value

class ScheduleOut(ScheduleCreate):
    # Existing schedules have no environment until explicitly edited.
    env_id: int | None = None
    id: int
    project_id: int
    sync_status: str
    sync_error: str | None = None
    model_config = ConfigDict(from_attributes=True)
