from pydantic import BaseModel, ConfigDict

class ScheduleCreate(BaseModel):
    name: str
    cron: str
    tag: str | None = None
    enabled: bool = True



class ScheduleOut(ScheduleCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)













