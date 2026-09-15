"""登录 / 注册：Argon2 用户表 + 按 IP 限流。租户取自用户记录，不接受客户端伪造。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api.auth.client_ip import client_ip
from api.auth.jwt_auth import create_access_token
from api.auth.user_store import authenticate, create_user
from config.settings import get_settings
from safety.http_rate_limit import allow_request

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=128)
    password: str = Field(..., min_length=8, max_length=256)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_enabled: bool
    user_id: str
    tenant_id: str


@router.post("/login", response_model=AuthTokenResponse)
async def login(req: LoginRequest, request: Request) -> AuthTokenResponse:
    settings = get_settings()
    ip = client_ip(request)
    if not await allow_request(f"login:{ip}", settings.login_rate_limit, 60):
        raise HTTPException(status_code=429, detail="登录尝试过多，请稍后再试")

    user = authenticate(req.username.strip(), req.password)
    if user is None:
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    token = create_access_token(subject=user.username, tenant_id=user.tenant_id)
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        auth_enabled=settings.auth_enabled,
        user_id=user.username,
        tenant_id=user.tenant_id,
    )


@router.post("/register", response_model=AuthTokenResponse)
async def register(req: RegisterRequest, request: Request) -> AuthTokenResponse:
    settings = get_settings()
    if not settings.allow_register:
        raise HTTPException(status_code=404, detail="未开放注册")

    ip = client_ip(request)
    if not await allow_request(f"register:{ip}", settings.login_rate_limit, 60):
        raise HTTPException(status_code=429, detail="尝试过多，请稍后再试")

    try:
        user = create_user(req.username.strip(), req.password)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    token = create_access_token(subject=user.username, tenant_id=user.tenant_id)
    return AuthTokenResponse(
        access_token=token,
        token_type="bearer",
        auth_enabled=settings.auth_enabled,
        user_id=user.username,
        tenant_id=user.tenant_id,
    )
