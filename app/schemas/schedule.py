from pydantic import ConfigDict, field_validator
from celery.schedules import crontab
from app.schemas.base import NamedSchema

class ScheduleCreate(NamedSchema):
    cron: str
    tag: str | None = None
    enabled: bool = True

    @field_validator("cron")
    @classmethod
    def validate_cron(cls, value: str) -> str:
        value = value.strip()
        fields = value.split()
        if len(fields) != 5:
            raise ValueError("Cron 必须包含 5 个字段")
        try:
            crontab(
                minute=fields[0],
                hour=fields[1],
                day_of_month=fields[2],
                month_of_year=fields[3],
                day_of_week=fields[4],
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("Cron 表达式不合法") from exc
        return value


class ScheduleOut(ScheduleCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)













