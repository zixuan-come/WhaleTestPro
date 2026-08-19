from typing import Generic, TypeVar

from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Common envelope for business API responses."""

    code: int
    message: str
    data: T | None = None


def success_response(data=None, message="\u64cd\u4f5c\u6210\u529f", status_code=200):
    return JSONResponse(
        status_code=status_code,
        content={"code": 0, "message": message, "data": jsonable_encoder(data)},
    )