"""启动时检查鉴权相关配置，避免带着默认密钥上线。"""

from __future__ import annotations

import logging

from config.settings import Settings

logger = logging.getLogger(__name__)

_WEAK_JWT_SECRETS = {
    "change-me-to-long-random",
    "change-me-to-long-random-at-least-32-chars",
    "secret",
    "jwt-secret",
}


class SecurityConfigError(RuntimeError):
    """生产/鉴权配置不合格，应阻止进程对外服务。"""


def assert_auth_config(settings: Settings) -> None:
    if settings.auth_enabled:
        secret = (settings.jwt_secret or "").strip()
        if len(secret) < 32 or secret in _WEAK_JWT_SECRETS:
            raise SecurityConfigError(
                "AUTH_ENABLED=true 时 JWT_SECRET 必须至少 32 字符，且不能使用示例默认值"
            )
        if settings.auth_debug_enabled:
            logger.error("AUTH_DEBUG_ENABLED=true：/api/auth/dev-token 可无密码签发 JWT")
        if settings.openapi_enabled:
            logger.error("OPENAPI_ENABLED=true：Swagger 对外暴露接口契约")

    if not settings.strict_production:
        return

    problems: list[str] = []
    if not settings.auth_enabled:
        problems.append("STRICT_PRODUCTION 要求 AUTH_ENABLED=true")
    if settings.auth_debug_enabled:
        problems.append("STRICT_PRODUCTION 要求 AUTH_DEBUG_ENABLED=false")
    if settings.openapi_enabled:
        problems.append("STRICT_PRODUCTION 要求 OPENAPI_ENABLED=false")
    if settings.enable_execute_python:
        problems.append("STRICT_PRODUCTION 要求 ENABLE_EXECUTE_PYTHON=false")
    if settings.admin_password == "admin123456":
        problems.append("STRICT_PRODUCTION 禁止使用默认 ADMIN_PASSWORD")
    origins = settings.cors_origin_list()
    if any(o in {"*", "null"} for o in origins):
        problems.append("STRICT_PRODUCTION 禁止 CORS 使用 * 或 null")
    if settings.rate_limit_backend != "redis":
        problems.append("STRICT_PRODUCTION 要求 RATE_LIMIT_BACKEND=redis")
    if settings.search_ssl_verify is False:
        problems.append("STRICT_PRODUCTION 要求 SEARCH_SSL_VERIFY=true")
    if problems:
        raise SecurityConfigError("; ".join(problems))
