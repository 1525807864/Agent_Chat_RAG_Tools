"""统一业务错误码与异常类型。

设计意图
========
- 应用层抛 ``AppError``，接口层映射为 HTTP / CLI 友好输出。
- ``detail`` 面向调用方；``internal`` 仅记日志，避免把密钥、堆栈、绝对路径
  原样回传给客户端（商业可用性与安全边界）。
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class ErrorCode(str, Enum):
    """稳定错误码，便于前端与运维对接（勿随意改字符串值）。"""

    VALIDATION = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    RATE_LIMITED = "RATE_LIMITED"
    CONTENT_BLOCKED = "CONTENT_BLOCKED"
    PATH_DENIED = "PATH_DENIED"
    DEPENDENCY = "DEPENDENCY_ERROR"
    INTERNAL = "INTERNAL_ERROR"
    UNAUTHORIZED = "UNAUTHORIZED"


class AppError(Exception):
    """应用层可预期错误。

    Parameters
    ----------
    code:
        稳定错误码。
    message:
        可对用户展示的简短说明（不含敏感信息）。
    http_status:
        接口层映射用的建议 HTTP 状态码。
    internal:
        仅日志使用的内部细节。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        http_status: int = 400,
        internal: Optional[str] = None,
        extras: Optional[dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.internal = internal
        self.extras = extras or {}

    def to_public_dict(self) -> dict[str, Any]:
        """序列化为可安全返回给客户端的结构。"""
        body: dict[str, Any] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.extras:
            body["extras"] = self.extras
        return body


def sanitize_exception_message(exc: BaseException) -> str:
    """把未知异常压成安全短句，避免 API Key / 路径泄漏。"""
    text = str(exc)
    lowered = text.lower()
    if "api_key" in lowered or "apikey" in lowered or "authorization" in lowered:
        return "上游服务认证失败"
    if "traceback" in lowered:
        return "内部处理失败"
    # 截断过长异常文本
    if len(text) > 300:
        return text[:300] + "..."
    return text or "未知错误"
