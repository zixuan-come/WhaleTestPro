import asyncio
import json

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from starlette.requests import Request

from app.core.exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.schemas.response import ApiResponse, success_response


def _json_body(response):
    return json.loads(response.body)


def _request(path="/test"):
    return Request({
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": [],
        "query_string": b"",
    })


def test_success_response_uses_common_envelope():
    model = ApiResponse[int](code=0, message="ok", data=1)
    response = success_response(model.data, model.message)

    assert response.status_code == 200
    assert _json_body(response) == {"code": 0, "message": "ok", "data": 1}


def test_http_exception_handler_uses_common_error_envelope():
    response = asyncio.run(
        http_exception_handler(_request(), HTTPException(status_code=404, detail="missing"))
    )

    assert response.status_code == 404
    assert _json_body(response) == {"code": 404, "message": "missing", "data": None}


def test_validation_exception_handler_keeps_field_errors():
    error = RequestValidationError([
        {
            "type": "missing",
            "loc": ("body", "name"),
            "msg": "Field required",
            "input": None,
        }
    ])
    response = asyncio.run(validation_exception_handler(_request(), error))
    body = _json_body(response)

    assert response.status_code == 422
    assert body["code"] == 422
    assert body["data"]["errors"] == [{"field": "name", "message": "Field required"}]


def test_unhandled_exception_handler_hides_internal_error():
    response = asyncio.run(
        unhandled_exception_handler(_request(), RuntimeError("secret database detail"))
    )
    body = _json_body(response)

    assert response.status_code == 500
    assert body == {"code": 500, "message": "服务器内部错误", "data": None}
