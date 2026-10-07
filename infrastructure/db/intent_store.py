"""P3：意图追踪三表落库（失败不影响主对话）。

与 agent_audit.py 同风格：pymysql 短连接 + safe_* 吞异常。
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def _mysql_datetime(iso: str) -> str | None:
    """ISO8601 → 'YYYY-MM-DD HH:MM:SS.ffffff'；空返回 None。"""
    raw = (iso or "").strip()
    if not raw:
        return None
    raw = raw.replace("T", " ")
    raw = raw.split("+")[0].split("Z")[0].strip()
    return raw[:26] or None


def safe_upsert_anchor(
    *,
    tenant_id: str,
    session_id: str,
    plan: dict[str, Any],
) -> None:
    """UPSERT intent_anchors（一会话一行）。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intent_anchors
                      (tenant_id, session_id, goal, goal_raw, anchor_history_json,
                       turn_created, last_confirmed_turn, status, version)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s)
                    ON DUPLICATE KEY UPDATE
                      goal=VALUES(goal),
                      goal_raw=VALUES(goal_raw),
                      anchor_history_json=VALUES(anchor_history_json),
                      turn_created=VALUES(turn_created),
                      last_confirmed_turn=VALUES(last_confirmed_turn),
                      status='active',
                      version=VALUES(version)
                    """,
                    (
                        tenant_id or "default",
                        session_id or "default",
                        str(plan.get("goal") or "")[:2000],
                        str(plan.get("goal_raw") or "") or None,
                        json.dumps(
                            plan.get("anchor_history") or [], ensure_ascii=False
                        ),
                        int(plan.get("turn_created") or 1),
                        int(plan.get("last_confirmed_turn") or 0),
                        int(plan.get("version") or 1),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.warning("safe_upsert_anchor 失败: %s", e)


def safe_upsert_tasks(
    *,
    tenant_id: str,
    session_id: str,
    anchor_version: int,
    tasks: list[dict[str, Any]],
) -> None:
    """UPSERT intent_tasks（一行一任务）。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                for t in tasks:
                    if not isinstance(t, dict) or not t.get("id") or not t.get("title"):
                        continue
                    cur.execute(
                        """
                        INSERT INTO intent_tasks
                          (id, tenant_id, session_id, anchor_version, title,
                           status, closed_by, sort_order, closed_at)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        ON DUPLICATE KEY UPDATE
                          title=VALUES(title),
                          status=VALUES(status),
                          closed_by=VALUES(closed_by),
                          sort_order=VALUES(sort_order),
                          closed_at=COALESCE(VALUES(closed_at), closed_at)
                        """,
                        (
                            str(t["id"])[:64],
                            tenant_id or "default",
                            session_id or "default",
                            int(anchor_version or 1),
                            str(t.get("title") or "")[:512],
                            str(t.get("status") or "pending")[:32],
                            str(t.get("closed_by") or "")[:32] or None,
                            int(t.get("sort") or 0),
                            _mysql_datetime(str(t.get("closed_at") or "")),
                        ),
                    )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.warning("safe_upsert_tasks 失败: %s", e)


def safe_record_check(
    *,
    tenant_id: str,
    session_id: str,
    turn_no: int,
    step_no: int,
    phase: str,
    verdict: str,
    reason: str = "",
    correction: str = "",
    action_json: dict[str, Any] | None = None,
    latency_ms: int = 0,
    model: str = "",
) -> None:
    """append-only 对齐检查审计。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO intent_checks
                      (tenant_id, session_id, turn_no, step_no, phase, verdict,
                       reason, correction, action_json, latency_ms, model)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        tenant_id or "default",
                        session_id or "default",
                        int(turn_no or 0),
                        int(step_no or 0),
                        str(phase or "")[:32],
                        str(verdict or "")[:32],
                        (str(reason or "")[:1000] or None),
                        (str(correction or "")[:1000] or None),
                        json.dumps(action_json, ensure_ascii=False)
                        if action_json
                        else None,
                        int(latency_ms or 0),
                        str(model or "")[:128] or None,
                    ),
                )
            conn.commit()
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.warning("safe_record_check 失败: %s", e)


def load_plan(*, tenant_id: str, session_id: str) -> dict[str, Any] | None:
    """按 P3 表重建 TaskPlan dict；无数据 / 库挂了返回 None。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT goal, goal_raw, anchor_history_json, turn_created,
                           last_confirmed_turn, version
                    FROM intent_anchors
                    WHERE tenant_id=%s AND session_id=%s AND status='active'
                    """,
                    (tenant_id or "default", session_id or "default"),
                )
                row = cur.fetchone()
                if not row:
                    return None
                cur.execute(
                    """
                    SELECT id, title, status, closed_by, closed_at, sort_order
                    FROM intent_tasks
                    WHERE tenant_id=%s AND session_id=%s
                    ORDER BY sort_order
                    """,
                    (tenant_id or "default", session_id or "default"),
                )
                task_rows = cur.fetchall()
        finally:
            conn.close()

        history = row.get("anchor_history_json") or []
        if isinstance(history, str):
            try:
                history = json.loads(history)
            except Exception:  # noqa: BLE001
                history = []
        return {
            "schema_version": 1,
            "session_id": session_id,
            "goal": str(row.get("goal") or ""),
            "goal_raw": str(row.get("goal_raw") or ""),
            "turn_created": int(row.get("turn_created") or 1),
            "last_confirmed_turn": int(row.get("last_confirmed_turn") or 0),
            "anchor_history": history or [],
            "tasks": [
                {
                    "id": str(t.get("id") or ""),
                    "title": str(t.get("title") or ""),
                    "status": str(t.get("status") or "pending"),
                    "closed_by": str(t.get("closed_by") or ""),
                    "closed_at": str(t.get("closed_at") or ""),
                    "sort": int(t.get("sort_order") or 0),
                }
                for t in task_rows
            ],
            "version": int(row.get("version") or 1),
            "check_errors": 0,
            "drift_count": 0,
            "blocked_actions": 0,
            "last_check": {},
        }
    except Exception as e:  # noqa: BLE001
        _log.warning("load_plan 失败: %s", e)
        return None
