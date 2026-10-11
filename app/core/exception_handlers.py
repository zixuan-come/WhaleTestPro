import logging
import traceback
from pathlib import Path

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


logger = logging.getLogger(__name__)


def _message_from_detail(detail):
    if isinstance(detail, str):
        return detail, None
    if isinstance(detail, dict):
        message = detail.get("message") or detail.get("detail") or "\u8bf7\u6c42\u5931\u8d25"
        return str(message), detail.get("data")
    return "\u8bf7\u6c42\u5931\u8d25", detail


def _error_response(code, message, data=None, headers=None):
    return JSONResponse(
        status_code=code,
        content={"code": code, "message": message, "data": data},
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    message, data = _message_from_detail(exc.detail)
    return _error_response(exc.status_code, message, data, exc.headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        location = error.get("loc", ())
        field = ".".join(
            str(item)
            for item in location
            if item not in {"body", "query", "path", "header"}
        )
        errors.append({
            "field": field or None,
            "message": error.get("msg", "\u53c2\u6570\u6821\u9a8c\u5931\u8d25"),
        })
    return _error_response(
        422,
        "\u8bf7\u6c42\u53c2\u6570\u6821\u9a8c\u5931\u8d25",
        {"errors": errors},
    )


async def unhandled_exception_handler(request: Request, exc: Exception):
    # Do not format exceptions: SQL parameters, driver errors and raw URLs can
    # contain credentials. Stack locations retain actionable diagnostics.
    route = getattr(request.scope.get("route"), "path", "<unmatched>")
    locations = [f"{Path(frame.filename).name}:{frame.lineno}:{frame.name}"
                 for frame in traceback.extract_tb(exc.__traceback__)[-16:]]
    logger.error(
        "Unhandled %s while processing %s %s; stack=%s",
        type(exc).__name__,
        request.method,
        route,
        " -> ".join(locations),
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "\u670d\u52a1\u5668\u5185\u90e8\u9519\u8bef",
    )


class SafeErrorMiddleware:
    """Prevent Starlette's 500 re-raise from leaking raw errors to server logs."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        response_started = False

        async def track_send(message):
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, track_send)
        except Exception as exc:
            response = await unhandled_exception_handler(Request(scope), exc)
            if response_started:
                # Never send a second response. Abort with a sanitized error;
                # "from None" prevents logging the original exception chain.
                raise RuntimeError(f"HTTP response aborted: {type(exc).__name__}") from None
            await response(scope, receive, send)
