"""可观测：request_id + 结构化日志。"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

logger = logging.getLogger("app.trace")

_request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def new_request_id() -> str:
    return uuid.uuid4().hex[:12]


def set_request_id(rid: str) -> None:
    _request_id_var.set(rid)


def get_request_id() -> str:
    return _request_id_var.get() or ""


def trace(event: str, **fields: object) -> None:
    rid = get_request_id()
    extra = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.info("request_id=%s event=%s %s", rid, event, extra)
