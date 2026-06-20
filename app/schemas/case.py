from pydantic import BaseModel, ConfigDict

class CaseCreate(BaseModel):
    name: str
    interface_id: int
    expected_status: int


class CaseOut(CaseCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)




