"""Safe protocol errors: never serialize request input or database diagnostics."""

from typing import Any
from uuid import uuid4

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after: int | None = None):
        self.status = status
        self.code = code
        self.message = message
        self.retry_after = retry_after
        super().__init__(code)


def error_response(error: ApiError, request_id: str) -> JSONResponse:
    headers = {"Cache-Control": "no-store", "X-Request-ID": request_id}
    if error.retry_after is not None:
        headers["Retry-After"] = str(error.retry_after)
    return JSONResponse(
        {
            "code": error.code,
            "message": error.message,
            "request_id": request_id,
            "retryable": error.status in {429, 503},
        },
        status_code=error.status,
        headers=headers,
    )


def install_error_handlers(app: FastAPI) -> None:
    async def handler(request: Request, error: Any) -> JSONResponse:
        if isinstance(error, ApiError):
            safe = error
        elif isinstance(error, RequestValidationError):
            safe = ApiError(422, "invalid_request", "Request fields do not match the API schema.")
        elif isinstance(error, psycopg.OperationalError):
            safe = ApiError(503, "storage_unavailable", "Local storage is temporarily unavailable.")
        elif isinstance(error, HTTPException):
            safe = ApiError(
                error.status_code, "object_not_found", "The requested route is unavailable."
            )
        else:
            safe = ApiError(500, "internal_error", "The request could not be completed.")
        return error_response(safe, getattr(request.state, "request_id", "req_" + uuid4().hex))

    for kind in (ApiError, RequestValidationError, psycopg.Error, HTTPException, Exception):
        app.add_exception_handler(kind, handler)
