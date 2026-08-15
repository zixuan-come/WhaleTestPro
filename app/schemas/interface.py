from pydantic import BaseModel, ConfigDict
from app.schemas.base import NamedSchema

class InterfaceCreate(NamedSchema):
    method: str
    url: str
    headers: dict | None = None
    params: dict | None = None
    body: dict | None = None
    category: str | None = None



class InterfaceOut(InterfaceCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)


class CategoryRename(BaseModel):
    old_name: str
    new_name: str










