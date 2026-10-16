"""登录 / 注册用例编排。

边界：
- 本模块不 import FastAPI / HTTPException（由 api/routes 映射状态码）
- 持久化走 api.auth.user_store；JWT 走 api.auth.jwt_auth
- 限流走 safety.http_rate_limit
"""

from __future__ import annotations

from dataclasses import dataclass

from api.auth.jwt_auth import create_access_token
from api.auth.user_store import authenticate, create_user
from api.auth.username_rules import USERNAME_RULE_MSG
from config.settings import get_settings
from safety.http_rate_limit import allow_request
from utils.logger import get_logger

_log = get_logger("nexora.auth.service")


@dataclass(frozen=True)
class AuthResult:
    """登录/注册成功后的令牌与身份信息。"""

    access_token: str
    user_id: str
    tenant_id: str
    auth_enabled: bool


class AuthError(Exception):
    """应用层鉴权失败；路由按 code 转 HTTP。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code  # unauthorized | conflict | rate_limited | disabled | invalid
        self.message = message


class AuthService:
    """鉴权应用服务（可单测、可被非 HTTP 入口复用）。"""

    async def login(
        self, *, username: str, password: str, client_ip: str
    ) -> AuthResult:
        settings = get_settings()
        # username 应由调用方先 normalize；此处再 strip 一次防内部直调
        name = (username or "").strip()
        if not await allow_request(
            f"login:{client_ip}", settings.login_rate_limit, 60
        ):
            _log.warning("登录限流 username=%s ip=%s", name, client_ip)
            raise AuthError("rate_limited", "登录尝试过多，请稍后再试")

        user = authenticate(name, password)
        if user is None:
            _log.warning("登录失败 username=%s ip=%s", name, client_ip)
            raise AuthError("unauthorized", "用户名或密码错误")

        # 旧库迁移：租户尚无成员时，把当前登录用户写成 owner
        try:
            from application.access.factory import get_access_service

            get_access_service().maybe_bootstrap_owner_on_login(
                user.tenant_id, user.username
            )
        except Exception:  # noqa: BLE001
            _log.warning(
                "登录后成员引导失败 username=%s", user.username, exc_info=True
            )

        token = create_access_token(subject=user.username, tenant_id=user.tenant_id)
        _log.info(
            "登录成功 username=%s tenant_id=%s ip=%s",
            user.username,
            user.tenant_id,
            client_ip,
        )
        return AuthResult(
            access_token=token,
            user_id=user.username,
            tenant_id=user.tenant_id,
            auth_enabled=settings.auth_enabled,
        )

    async def register(
        self, *, username: str, password: str, client_ip: str
    ) -> AuthResult:
        settings = get_settings()
        if not settings.allow_register:
            raise AuthError("disabled", "未开放注册")

        name = (username or "").strip()
        if not await allow_request(
            f"register:{client_ip}", settings.login_rate_limit, 60
        ):
            raise AuthError("rate_limited", "尝试过多，请稍后再试")

        try:
            # 用户名即租户号；create_user 内会 normalize 格式
            user = create_user(name, password, tenant_id=name)
        except ValueError as exc:
            msg = str(exc)
            _log.warning(
                "注册失败 username=%s ip=%s detail=%s", name, client_ip, msg
            )
            if msg == USERNAME_RULE_MSG or msg.startswith("用户名须"):
                raise AuthError("invalid", msg) from exc
            raise AuthError("conflict", msg) from exc

        # 注册成功：写入租户 owner（与 users 表同一事务外尽力而为）
        try:
            from application.access.factory import get_access_service

            get_access_service().bootstrap_owner_on_register(
                user.tenant_id, user.username
            )
        except Exception:  # noqa: BLE001
            _log.warning(
                "注册后写入 owner 失败 username=%s", user.username, exc_info=True
            )

        token = create_access_token(subject=user.username, tenant_id=user.tenant_id)
        _log.info(
            "注册成功 username=%s tenant_id=%s ip=%s",
            user.username,
            user.tenant_id,
            client_ip,
        )
        return AuthResult(
            access_token=token,
            user_id=user.username,
            tenant_id=user.tenant_id,
            auth_enabled=settings.auth_enabled,
        )


_auth_service: AuthService | None = None


def get_auth_service() -> AuthService:
    """进程内单例；测试可直接 AuthService()。"""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service
