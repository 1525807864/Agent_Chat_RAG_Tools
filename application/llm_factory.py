"""按请求解析 ChatModel（请求级 Key 覆盖，不污染进程单例）。"""

from __future__ import annotations

from typing import Any

from infrastructure.llm.deepseek import DeepSeekChatModel
from shared.errors import AppError, ErrorCode


def resolve_request_llm(
    settings: Any,
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    model_name: str | None = None,
    temperature: float | None = None,
) -> DeepSeekChatModel:
    """优先级：本轮参数 > Settings/.env。空字符串视为未提供。"""
    key = (api_key or "").strip() or (settings.deepseek_api_key or "").strip()
    base = (api_base or "").strip() or (settings.deepseek_api_base or "").strip()
    model = (model_name or "").strip() or (settings.model_name or "").strip()
    temp = (
        settings.model_temperature if temperature is None else float(temperature)
    )

    if not key:
        raise AppError(
            ErrorCode.UNAUTHORIZED,
            "请先在设置中填写 API Key，或在服务端 .env 配置 DEEPSEEK_API_KEY",
            http_status=401,
        )
    if not base:
        raise AppError(
            ErrorCode.VALIDATION,
            "请填写 API Base（例如 https://api.deepseek.com/v1）",
            http_status=400,
        )

    return DeepSeekChatModel(
        model_name=model,
        temperature=temp,
        max_tokens=settings.model_max_tokens,
        api_key=key,
        api_base=base,
    )
