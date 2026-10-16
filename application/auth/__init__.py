"""鉴权应用服务：登录 / 注册编排（不含 FastAPI）。"""

from application.auth.service import AuthError, AuthResult, AuthService, get_auth_service

__all__ = ["AuthError", "AuthResult", "AuthService", "get_auth_service"]
