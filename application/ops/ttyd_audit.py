"""交互终端审计（P2）。

只记元数据：谁、何时、哪个 sandbox_session、启停、只读否。
不把 PTY 字节流默认落库（P4 才做录制）。
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from shared.path_security import get_project_root
from shared.timeutil import now_iso

_log = logging.getLogger("nexora.ops.ttyd.audit")


def _path() -> Path:
    p = get_project_root() / "data" / "ops" / "terminal_audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def audit_terminal(event: str, **fields: Any) -> None:
    """追加一行 JSONL，同时打结构化日志。"""
    row = {"ts": now_iso(), "event": event, **fields}
    line = json.dumps(row, ensure_ascii=False)
    _log.info("ttyd.audit %s", line)
    try:
        with _path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        _log.exception("ttyd.audit write failed")
