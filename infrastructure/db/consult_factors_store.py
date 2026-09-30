"""P1：consult 会话因子（MySQL 优先，失败回退 JSON 文件）。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor

    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def load_factors_mysql(tenant_id: str, session_id: str) -> dict[str, str] | None:
    """成功返回 dict；库不可用返回 None。"""
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT factors_json FROM consult_factors
                    WHERE tenant_id=%s AND session_id=%s
                    """,
                    (tenant_id, session_id),
                )
                row = cur.fetchone()
            if not row:
                return {}
            raw = row.get("factors_json")
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8")
            if isinstance(raw, str):
                data = json.loads(raw)
            elif isinstance(raw, dict):
                data = raw
            else:
                return {}
            return {str(k): str(v) for k, v in data.items() if v is not None}
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("load_factors_mysql 回退文件: %s", e)
        return None


def save_factors_mysql(
    tenant_id: str, session_id: str, factors: dict[str, Any]
) -> bool:
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO consult_factors (tenant_id, session_id, factors_json)
                    VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE factors_json=VALUES(factors_json)
                    """,
                    (
                        tenant_id,
                        session_id,
                        json.dumps(factors or {}, ensure_ascii=False),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        _log.debug("save_factors_mysql 回退文件: %s", e)
        return False


def load_session_factors(
    *,
    tenant_id: str,
    session_id: str,
    file_path: Path,
    suffix: str = "",
) -> dict[str, str]:
    """MySQL 有数据用库；否则读文件模板。"""
    from rag.structured.records import load_session_factors as load_file
    from rag.structured.schema import empty_factor_dict

    base = empty_factor_dict(suffix)
    mysql_data = load_factors_mysql(tenant_id, session_id)
    if mysql_data is not None and mysql_data:
        merged = dict(base)
        merged.update(mysql_data)
        return merged
    if mysql_data is not None and not mysql_data:
        # 库通但无行 → 仍可尝试文件（迁移期）
        file_data = load_file(file_path, suffix=suffix)
        if any(file_data.values()):
            return file_data
        return base
    return load_file(file_path, suffix=suffix)


def save_session_factors(
    *,
    tenant_id: str,
    session_id: str,
    file_path: Path,
    factors: dict[str, str],
) -> None:
    """双写：优先 MySQL，并始终写文件作备份。"""
    from rag.structured.records import save_session_factors as save_file

    save_factors_mysql(tenant_id, session_id, factors)
    save_file(file_path, factors)
