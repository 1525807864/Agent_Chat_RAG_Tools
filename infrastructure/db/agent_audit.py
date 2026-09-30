"""P1：agent_runs / tool_invocations 审计落库（失败不影响主对话）。"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any

_log = logging.getLogger(__name__)


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def new_run_id() -> str:
    return uuid.uuid4().hex


def safe_record_run(
    *,
    tenant_id: str,
    session_id: str,
    mode: str = "agent",
    model: str | None = None,
    status: str = "ok",
    answer: str = "",
    tokens_in: int = 0,
    tokens_out: int = 0,
    latency_ms: int = 0,
    error_message: str | None = None,
    tool_calls: list[dict] | None = None,
) -> str | None:
    """成功返回 run_id；库挂了返回 None。"""
    run_id = new_run_id()
    preview = (answer or "")[:500]
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runs
                      (id, tenant_id, session_id, mode, model, status,
                       answer_preview, tokens_in, tokens_out, latency_ms, error_message)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        run_id,
                        tenant_id or "default",
                        session_id or "default",
                        mode,
                        model,
                        status,
                        preview,
                        int(tokens_in),
                        int(tokens_out),
                        int(latency_ms),
                        ((error_message or "")[:1000] or None),
                    ),
                )
                for tc in tool_calls or []:
                    name = str(tc.get("tool") or tc.get("name") or "")
                    if not name:
                        continue
                    cur.execute(
                        """
                        INSERT INTO tool_invocations
                          (run_id, tenant_id, session_id, tool_name,
                           input_json, output_preview, forced)
                        VALUES (%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            run_id,
                            tenant_id or "default",
                            session_id or "default",
                            name,
                            json.dumps(tc.get("input") or {}, ensure_ascii=False),
                            str(tc.get("output") or "")[:2000],
                            1 if tc.get("forced") else 0,
                        ),
                    )
            conn.commit()
        finally:
            conn.close()
        return run_id
    except Exception as e:  # noqa: BLE001
        _log.warning("safe_record_run 失败: %s", e)
        return None
