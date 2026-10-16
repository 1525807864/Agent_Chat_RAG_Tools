"""登录 / 注册 HTTP 适配器：校验入参 → 调 AuthService → 映射状态码。"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from api.auth.client_ip import client_ip
from api.auth.username_rules import normalize_new_username
from application.auth import AuthError, AuthResult, get_auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1, max_length=256)

    @field_validator("username")
    @classmethod
    def username_no_casefold(cls, value: str) -> str:
        """只 strip+格式校验，绝不 lower；大小写由客户端原样提交。"""
        return normalize_new_username(value)


class RegisterRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=32)
    password: str = Field(..., min_length=8, max_length=256)

    @field_validator("username")
    @classmethod
    def username_charset(cls, value: str) -> str:
        """与 create_user / AuthService 同一规则。"""
        return normalize_new_username(value)


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    auth_enabled: bool
    user_id: str
    tenant_id: str


def _to_http(err: AuthError) -> HTTPException:
    """应用层错误码 → HTTP。"""
    status = {
        "unauthorized": 401,
        "conflict": 409,
        "rate_limited": 429,
        "disabled": 404,
        "invalid": 422,
    }.get(err.code, 400)
    return HTTPException(status_code=status, detail=err.message)


def _to_response(result: AuthResult) -> AuthTokenResponse:
    return AuthTokenResponse(
        access_token=result.access_token,
        token_type="bearer",
        auth_enabled=result.auth_enabled,
        user_id=result.user_id,
        tenant_id=result.tenant_id,
    )


@router.post("/login", response_model=AuthTokenResponse)
async def login(req: LoginRequest, request: Request) -> AuthTokenResponse:
    try:
        result = await get_auth_service().login(
            username=req.username,
            password=req.password,
            client_ip=client_ip(request),
        )
    except AuthError as exc:
        raise _to_http(exc) from exc
    return _to_response(result)


@router.post("/register", response_model=AuthTokenResponse)
async def register(req: RegisterRequest, request: Request) -> AuthTokenResponse:
    try:
        result = await get_auth_service().register(
            username=req.username,
            password=req.password,
            client_ip=client_ip(request),
        )
    except AuthError as exc:
        raise _to_http(exc) from exc
    return _to_response(result)
