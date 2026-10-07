"""LangSmith：进程级环境变量 + 每轮对话父 trace。

失败策略：未配密钥或 SDK 异常时静默关闭上报，不阻断对话。
不要把用户原文、API Key 写进 metadata。
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Iterator

from observability.tracing import get_request_id

logger = logging.getLogger("app.trace")

_CONFIGURED = False


def langsmith_ready(settings: Any | None = None) -> bool:
    """开关打开且有密钥才上报。"""
    if settings is None:
        from config.settings import get_settings

        settings = get_settings()
    if not bool(getattr(settings, "langsmith_tracing", False)):
        return False
    key = (getattr(settings, "langsmith_api_key", None) or "").strip()
    return bool(key)


def configure_langsmith(settings: Any) -> None:
    """启动时写入进程环境，供 LangChain 自动 Tracer 读取。只执行一次。"""
    global _CONFIGURED
    if _CONFIGURED:
        return
    _CONFIGURED = True

    enabled = bool(settings.langsmith_tracing)
    key = (settings.langsmith_api_key or "").strip()
    project = (settings.langsmith_project or "nexora").strip() or "nexora"
    endpoint = (settings.langsmith_endpoint or "").strip()

    if enabled and not key:
        logger.warning(
            "LANGSMITH_TRACING=true 但未配置 LANGSMITH_API_KEY，本进程不上报"
        )
        os.environ["LANGSMITH_TRACING"] = "false"
        os.environ["LANGCHAIN_TRACING_V2"] = "false"
        return

    if not enabled:
        os.environ.setdefault("LANGSMITH_TRACING", "false")
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "false")
        logger.info("LangSmith 未启用")
        return

    os.environ["LANGSMITH_TRACING"] = "true"
    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGSMITH_API_KEY"] = key
    os.environ["LANGCHAIN_API_KEY"] = key
    os.environ["LANGSMITH_PROJECT"] = project
    os.environ["LANGCHAIN_PROJECT"] = project
    if endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = endpoint
        os.environ["LANGCHAIN_ENDPOINT"] = endpoint
    logger.info("LangSmith 已启用 project=%s", project)


@contextmanager
def langsmith_turn(ctx: Any, *, name: str = "chat.turn") -> Iterator[None]:
    """把 handle/stream 整轮包进一条父 trace；tags 便于按 mode/tenant 过滤。"""
    try:
        from config.settings import get_settings

        settings = get_settings()
    except Exception:  # noqa: BLE001
        yield
        return

    if not langsmith_ready(settings):
        yield
        return

    tags = [
        f"mode:{getattr(ctx, 'mode', '') or 'unknown'}",
        f"tenant:{getattr(ctx, 'tenant_id', '') or 'default'}",
    ]
    metadata = {
        "request_id": get_request_id(),
        "session_id": getattr(ctx, "session_id", "") or "",
        "tenant_id": getattr(ctx, "tenant_id", "") or "",
        "mode": getattr(ctx, "mode", "") or "",
        "run_name": name,
    }
    project = (settings.langsmith_project or "nexora").strip() or "nexora"

    try:
        from langsmith import tracing_context
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangSmith SDK 不可用，跳过上报: %s", exc)
        yield
        return

    try:
        cm = tracing_context(
            project_name=project,
            enabled=True,
            tags=tags,
            metadata=metadata,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("LangSmith tracing_context 构造失败，本轮不上报: %s", exc)
        yield
        return

    try:
        with cm:
            yield
    except Exception:
        raise
