"""统一异常处理：将 AppError / 未知异常映射为安全的 HTTP 响应。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from observability.tracing import get_request_id
from shared.errors import AppError, ErrorCode, sanitize_exception_message

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册全局异常处理器。"""

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        logger.warning(
            "AppError request_id=%s path=%s code=%s message=%s internal=%s",
            get_request_id() or "-",
            request.url.path,
            exc.code.value,
            exc.message,
            exc.internal,
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_public_dict(),
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        # 401/404 用 warning，5xx 用 error
        log_fn = logger.error if exc.status_code >= 500 else logger.warning
        log_fn(
            "HTTPException request_id=%s path=%s status=%s detail=%s",
            get_request_id() or "-",
            request.url.path,
            exc.status_code,
            exc.detail,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        logger.warning(
            "ValidationError request_id=%s path=%s errors=%s",
            get_request_id() or "-",
            request.url.path,
            exc.errors(),
        )
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "未处理异常 request_id=%s path=%s type=%s: %s",
            get_request_id() or "-",
            request.url.path,
            type(exc).__name__,
            exc,
        )
        return JSONResponse(
            status_code=500,
            content={
                "code": ErrorCode.INTERNAL.value,
                "message": sanitize_exception_message(exc),
            },
        )
