from pydantic import BaseModel, ConfigDict, Field


class UserBase(BaseModel):
    username: str


class UserCreate(UserBase):
    username: str = Field(..., min_length=4, max_length=20)
    password: str = Field(..., min_length=4, max_length=20)


class UserLogin(UserBase):
    password: str


class UserOut(UserBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
