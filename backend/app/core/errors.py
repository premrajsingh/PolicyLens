from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppError(Exception):
    def __init__(self, message: str, *, status_code: int = 400, code: str = "app_error") -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def http_error_handler(_: Request, exc: HTTPException) -> JSONResponse:
    detail: Any = exc.detail
    if isinstance(detail, dict):
        return JSONResponse(status_code=exc.status_code, content={"error": detail})
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "http_error", "message": str(detail)}},
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = request.headers.get("x-request-id") or "-"
    logger.exception(
        "unhandled_error path=%s method=%s request_id=%s",
        request.url.path,
        request.method,
        request_id,
    )
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "internal_error", "message": "An unexpected error occurred."}},
    )
