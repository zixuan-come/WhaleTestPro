from pydantic import BaseModel, ConfigDict


class EnvironmentCreate(BaseModel):
    name: str
    base_url: str
    variables: dict | None = None


class EnvironmentOut(EnvironmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)






