from pydantic import ConfigDict
from app.schemas.base import NamedSchema

class MockCreate(NamedSchema):
    path: str
    method: str
    status: int = 200
    body: dict | None = None
    delay_ms: int = 0


class MockOut(MockCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)



