"""统一异常处理：将 AppError / 未知异常映射为安全的 HTTP 响应。"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from shared.errors import AppError, ErrorCode, sanitize_exception_message

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """在 FastAPI 应用上注册全局异常处理器。

    仅拦截 ``AppError`` 与真正的未处理异常；
    ``HTTPException`` / ``RequestValidationError`` 交回框架默认行为
    （通过显式注册保持原响应形状）。
    """

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
        if exc.internal:
            logger.warning(
                "AppError %s: %s | internal=%s",
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
        _request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_handler(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("未处理异常: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "code": ErrorCode.INTERNAL.value,
                "message": sanitize_exception_message(exc),
            },
        )
