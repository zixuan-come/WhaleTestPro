from pydantic import BaseModel, ConfigDict

class InterfaceCreate(BaseModel):
    name: str
    method: str
    url: str
    headers: dict | None = None
    params: dict | None = None
    body: dict | None = None




class InterfaceOut(InterfaceCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)










