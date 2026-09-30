"""P1：Cursor agent_id 绑定（MySQL 优先，失败回退 JSON 文件）。"""

from __future__ import annotations

import logging
from pathlib import Path

_log = logging.getLogger(__name__)


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def load_agent_id_mysql(tenant_id: str, session_id: str) -> str | None:
    """MySQL 读；失败返回 None 表示应走文件回退。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT agent_id FROM session_routing
                    WHERE tenant_id=%s AND session_id=%s
                    """,
                    (tenant_id, session_id),
                )
                row = cur.fetchone()
            return str((row or {}).get("agent_id") or "")
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("load_agent_id_mysql 回退文件: %s", e)
        return None


def save_agent_id_mysql(tenant_id: str, session_id: str, agent_id: str) -> bool:
    """写入成功 True；失败 False（调用方写文件）。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO session_routing (tenant_id, session_id, provider, agent_id)
                    VALUES (%s, %s, 'cursor', %s)
                    ON DUPLICATE KEY UPDATE
                        agent_id=VALUES(agent_id), provider='cursor'
                    """,
                    (tenant_id, session_id, agent_id or ""),
                )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        _log.debug("save_agent_id_mysql 回退文件: %s", e)
        return False


def load_agent_id(project_root: Path, tenant_id: str, session_id: str) -> str:
    """对外 API：保持与 application.routing.agent_store 相同签名。"""
    mysql_val = load_agent_id_mysql(tenant_id, session_id)
    if mysql_val is not None:
        return mysql_val
    from application.routing import agent_store as file_store

    return file_store.load_agent_id(project_root, tenant_id, session_id)


def save_agent_id(
    project_root: Path,
    tenant_id: str,
    session_id: str,
    agent_id: str,
) -> None:
    if save_agent_id_mysql(tenant_id, session_id, agent_id):
        return
    from application.routing import agent_store as file_store

    file_store.save_agent_id(project_root, tenant_id, session_id, agent_id)
