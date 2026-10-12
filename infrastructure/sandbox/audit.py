"""沙箱审计：命令进日志，不进密钥、不进完整超大输出。

估值级底线
==========
- 每条 exec 必须有 tenant / session / kind / argv 摘要 / exit / 耗时。
- argv 里疑似 token 的参数打码。
- 输出只记长度，避免把客户数据打进集中日志。
"""

from __future__ import annotations

import logging
import re
from typing import Any

from infrastructure.sandbox.models import ExecRequest, ExecResult

_log = logging.getLogger("nexora.sandbox.audit")

_SECRET = re.compile(r"(token|secret|password|api[_-]?key)=?\S+", re.I)


def _redact(parts: list[str]) -> list[str]:
    """打码疑似密钥；过长参数截断。"""
    out: list[str] = []
    for p in parts:
        if _SECRET.search(p):
            out.append("<redacted>")
        else:
            out.append(p[:200])
    return out


def log_exec(req: ExecRequest, result: ExecResult, *, vertical: str) -> None:
    """记录一次命令执行（不含完整 stdout/stderr 正文）。"""
    _log.info(
        "sandbox.exec tenant=%s session=%s vertical=%s kind=%s argv=%s "
        "exit=%s timeout=%s truncated=%s ms=%s out_len=%s err_len=%s",
        req.tenant_id,
        req.session_id,
        vertical,
        req.kind,
        _redact(req.argv),
        result.exit_code,
        result.timed_out,
        result.truncated,
        result.duration_ms,
        len(result.stdout),
        len(result.stderr),
    )


def log_lifecycle(event: str, **fields: Any) -> None:
    """记录 acquire / release / expire 等生命周期事件。"""
    kv = " ".join(f"{k}={v}" for k, v in fields.items())
    _log.info("sandbox.%s %s", event, kv)
