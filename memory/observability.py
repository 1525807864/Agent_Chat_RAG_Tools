"""记忆子系统运维可观测性（商业 Agent 标配）。

设计原则（对齐 Mem0 / Letta / 生产 LangGraph 服务）：
1. 关键路径必须打结构化日志（session / tenant / latency / 结果摘要）
2. 失败可观测但默认 fail-open（不拖垮主对话），由调用方决定是否升级为 fail-closed
3. 与 ``observability.tracing.trace`` 并存：本模块专注 memory 域事件
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Iterator

_log = logging.getLogger("memory.ops")


def memory_event(event: str, **fields: Any) -> None:
    """打一条结构化 INFO 日志，便于 ELK / Loki 检索。

    约定字段（有则带）：
      tenant_id, session_id, latency_ms, ok, reason, count, detail
    """
    # 过滤 None，避免日志噪声
    parts = [f"{k}={v!r}" for k, v in fields.items() if v is not None]
    _log.info("memory_event=%s %s", event, " ".join(parts))


def memory_warn(event: str, err: BaseException | str, **fields: Any) -> None:
    """可恢复错误：WARNING + 异常类型，禁止静默 swallow。"""
    parts = [f"{k}={v!r}" for k, v in fields.items() if v is not None]
    _log.warning(
        "memory_event=%s err=%s %s",
        event,
        err if isinstance(err, str) else f"{type(err).__name__}:{err}",
        " ".join(parts),
    )


@contextmanager
def memory_span(event: str, **fields: Any) -> Iterator[dict[str, Any]]:
    """计时上下文：退出时自动打 latency_ms。

    用法::
        with memory_span("load_turn", session_id=sid) as span:
            ...
            span["hits"] = 3
    """
    t0 = time.perf_counter()
    span: dict[str, Any] = dict(fields)
    span["ok"] = True
    try:
        yield span
    except Exception as e:  # noqa: BLE001
        span["ok"] = False
        span["error"] = f"{type(e).__name__}:{e}"
        raise
    finally:
        span["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        # 尝试挂到全局 request tracing（若存在）
        try:
            from observability.tracing import trace

            trace(f"memory_{event}", **{k: v for k, v in span.items() if k != "ok"})
        except Exception:  # noqa: BLE001
            pass
        memory_event(event, **span)
