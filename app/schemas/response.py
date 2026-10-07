from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """Common envelope for business API responses."""

    code: int
    message: str
    data: T | None = None


def success_response(data=None, message="\u64cd\u4f5c\u6210\u529f", status_code=200):
    # Keep ORM objects intact until FastAPI validates/filters response_model.
    # HTTP status is declared on the route, not in the business envelope.
    return {"code": 0, "message": message, "data": data}
