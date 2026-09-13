"""fastapi依赖 - 从 Authorization 头解析当前用户"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Header, HTTPException
from jwt import PyJWTError

from api.auth.jwt_auth import decode_access_token
from config.settings import get_settings


@dataclass
class AuthUser:
    """当前请求身份。

    示例::
        AuthUser(user_id="user_001", tenant_id="tenant_acme")
    """

    user_id: str
    tenant_id: str


async def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> AuthUser:
    """依赖注入：解析 Bearer Token。

    请求头示例::
        Authorization: Bearer eyJhbGciOi...

    返回示例::
        AuthUser(user_id="user_001", tenant_id="tenant_acme")
    """
    settings = get_settings()

    # 本地关闭鉴权：返回默认租户（方便 Electron / 调试）
    if not settings.auth_enabled:
        return AuthUser(user_id="anonymous", tenant_id=settings.default_tenant_id)

    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=401,
            detail="缺少 Authorization: Bearer <token>",
        )

    raw = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_access_token(raw)
    except PyJWTError as e:
        raise HTTPException(status_code=401, detail=f"无效的 Token: {e}") from e

    user_id = str(payload.get("sub") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "").strip()
    if not user_id or not tenant_id:
        raise HTTPException(status_code=401, detail="token 缺少 sub/tenant_id")

    return AuthUser(user_id=user_id, tenant_id=tenant_id)


# 给路由用的简写（等价于 Depends(get_current_user)）
RequireUser = Depends(get_current_user)
