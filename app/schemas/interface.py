from pydantic import BaseModel, ConfigDict

class InterfaceCreate(BaseModel):
    name: str
    method: str
    url: str


class InterfaceOut(InterfaceCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)










