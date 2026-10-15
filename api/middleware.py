"""安全响应头 + 就绪门闩 + 请求访问日志。

全站 /api IP 限流已关闭；登录/注册限流见 ``api/routes/auth_login.py``。
"""

from __future__ import annotations

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from observability.tracing import get_request_id, new_request_id, set_request_id

# /health、/health/live、/health/ready 都以 /health 开头，一并放行
_SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json")
_access_log = logging.getLogger("nexora.access")


class ReadinessGateMiddleware(BaseHTTPMiddleware):
    """未就绪时拒绝业务流量，避免半初始化接请求。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        if request.method == "OPTIONS" or any(
            path.startswith(p) for p in _SKIP_PREFIXES
        ):
            return await call_next(request)

        from api.health_state import health_state

        if not health_state.ready:
            _access_log.warning(
                "拒绝未就绪请求 method=%s path=%s startup_error=%s",
                request.method,
                path,
                health_state.startup_error,
            )
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "service not ready",
                    "startup_error": health_state.startup_error,
                },
                headers={"Retry-After": "3"},
            )
        return await call_next(request)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """为每个 HTTP 请求打访问日志（含耗时、状态码、request_id）。

    /health* 仅 DEBUG，避免探活刷屏。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path
        rid = request.headers.get("x-request-id") or new_request_id()
        set_request_id(rid)
        t0 = time.perf_counter()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers.setdefault("X-Request-Id", rid)
            return response
        except Exception:
            _access_log.exception(
                "request_id=%s method=%s path=%s 未捕获异常",
                rid,
                request.method,
                path,
            )
            raise
        finally:
            ms = round((time.perf_counter() - t0) * 1000, 1)
            quiet = path.startswith("/health")
            line = (
                "request_id=%s method=%s path=%s status=%s elapsed_ms=%s"
                % (get_request_id() or rid, request.method, path, status, ms)
            )
            if quiet:
                _access_log.debug(line)
            elif status >= 500:
                _access_log.error(line)
            elif status >= 400:
                _access_log.warning(line)
            else:
                _access_log.info(line)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Ops 终端 iframe 必须能被嵌入；全局 DENY 会导致浏览器显示「禁止」页
        # MutableHeaders 无 pop()，只能 del / setdefault
        path = request.url.path or ""
        if path.startswith("/api/ops/terminal/proxy"):
            if "x-frame-options" in response.headers:
                del response.headers["x-frame-options"]
        else:
            response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
        )
        response.headers.setdefault("X-XSS-Protection", "0")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security",
                "max-age=31536000; includeSubDomains",
            )
        return response


class ApiRateLimitMiddleware(BaseHTTPMiddleware):
    """全站 /api 限流已关闭（类保留便于以后重新启用）。"""

    async def dispatch(self, request: Request, call_next) -> Response:
        return await call_next(request)
