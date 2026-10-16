"""当前登录用户在本租户的角色与按钮权限。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
from application.access.factory import get_access_service
from application.access.service import AccessError
from config.settings import get_settings
from domain.access import ROLE_OWNER, permissions_for_role

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
async def me(user: AuthUser = Depends(get_current_user)):
    """前端藏按钮用；不能替代服务端 require_perm。"""
    settings = get_settings()
    if not settings.auth_enabled:
        return {
            "userId": user.user_id,
            "tenantId": user.tenant_id,
            "role": ROLE_OWNER,
            "permissions": permissions_for_role(ROLE_OWNER),
        }
    try:
        info = get_access_service().me(user.tenant_id, user.user_id)
    except AccessError as exc:
        raise HTTPException(status_code=403, detail=exc.message) from exc
    return {
        "userId": info.user_id,
        "tenantId": info.tenant_id,
        "role": info.role,
        "permissions": info.permissions,
    }
