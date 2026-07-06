from pydantic import BaseModel, ConfigDict

class InterfaceCreate(BaseModel):
    name: str
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










