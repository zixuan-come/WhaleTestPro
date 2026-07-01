from pydantic import BaseModel, ConfigDict

class DemoOrderCreate(BaseModel):
    item: str


class DemoOrderOut(DemoOrderCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)





