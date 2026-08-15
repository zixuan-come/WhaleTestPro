from pydantic import ConfigDict
from app.schemas.base import NamedSchema


class EnvironmentCreate(NamedSchema):
    base_url: str
    variables: dict | None = None


class EnvironmentOut(EnvironmentCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)






