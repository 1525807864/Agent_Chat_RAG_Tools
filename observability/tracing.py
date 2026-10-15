"""可观测：request_id + 结构化事件日志。"""

from __future__ import annotations

import logging
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator

logger = logging.getLogger("app.trace")

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(rid: str) -> None:
    _request_id_var.set(rid)


def get_request_id() -> str:
    return _request_id_var.get() or ""


def _fmt_fields(fields: dict) -> str:
    parts: list[str] = []
    for k, v in fields.items():
        if v is None:
            continue
        s = str(v)
        # 避免日志被超长正文淹没
        if len(s) > 300:
            s = s[:300] + "…"
        # 空格用短横，便于肉眼扫
        s = s.replace("\n", "\\n").replace(" ", "_")
        parts.append(f"{k}={s}")
    return " ".join(parts)


def trace(event: str, **fields: object) -> None:
    """INFO 级业务事件（带 request_id）。"""
    rid = get_request_id() or "-"
    extra = _fmt_fields(fields)
    if extra:
        logger.info("request_id=%s event=%s %s", rid, event, extra)
    else:
        logger.info("request_id=%s event=%s", rid, event)


def trace_warn(event: str, **fields: object) -> None:
    rid = get_request_id() or "-"
    logger.warning("request_id=%s event=%s %s", rid, event, _fmt_fields(fields))


def trace_error(event: str, exc: BaseException | None = None, **fields: object) -> None:
    """ERROR：可选附带异常栈。"""
    rid = get_request_id() or "-"
    msg = "request_id=%s event=%s %s" % (rid, event, _fmt_fields(fields))
    if exc is not None:
        logger.error(msg, exc_info=exc)
    else:
        logger.error(msg)


@contextmanager
def timed(event: str, **fields: object) -> Iterator[dict]:
    """计时上下文：退出时打 ``event_done`` 与 ``elapsed_ms``。

    Usage::
        with timed("chat_dispatch", mode=mode) as ctx:
            ...
            ctx["answer_len"] = len(answer)
    """
    bag: dict = dict(fields)
    t0 = time.perf_counter()
    trace(f"{event}_start", **bag)
    try:
        yield bag
    except Exception as exc:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        trace_error(
            f"{event}_failed",
            exc,
            elapsed_ms=elapsed,
            error_type=type(exc).__name__,
            **bag,
        )
        raise
    else:
        elapsed = round((time.perf_counter() - t0) * 1000, 1)
        trace(f"{event}_done", elapsed_ms=elapsed, **bag)
