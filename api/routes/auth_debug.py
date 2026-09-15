"""调试用：签发开发 Token（商用请换成正式登录，并限制此路由）。"""

from __future__ import annotations

from fastapi import APIRouter,HTTPException
from pydantic import BaseModel, Field

from api.auth.jwt_auth import create_access_token
from config.settings import get_settings

router = APIRouter(prefix="/api/auth", tags=["auth"])


class DevTokenRequest(BaseModel):
    """POST /api/auth/dev-token 请求体。"""

    user_id: str = Field(default="user_001", min_length=1, max_length=128)
    tenant_id: str = Field(default="default", min_length=1, max_length=128)


class DevTokenResponse(BaseModel):
    """返回示例::
        {"access_token": "eyJ...", "token_type": "bearer", "auth_enabled": true}
    """

    access_token: str
    token_type: str = "bearer"
    auth_enabled: bool


@router.post("/dev-token", response_model=DevTokenResponse)
async def issue_dev_token(req: DevTokenRequest) -> DevTokenResponse:
    """仅开发联调使用，生产环境AUTH_DEBUG_ENABLED=false时路由根本不会注册"""
    settings = get_settings()
    #双保险
    if not settings.auth_debug_enabled:
        raise HTTPException(status_code=404,detail="路由未启用")
    token = create_access_token(subject=req.user_id, tenant_id=req.tenant_id)
    return DevTokenResponse(
        access_token=token,
        token_type="bearer",
        auth_enabled=settings.auth_enabled,
    )
