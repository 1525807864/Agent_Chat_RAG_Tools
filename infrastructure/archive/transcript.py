"""P2：会话 transcript JSONL 归档（DB 只存指针）。"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def archive_session_jsonl(
    messages: list[dict],
    *,
    root: Path,
    tenant_id: str,
    session_id: str,
) -> tuple[str, int]:
    """写入 archives/{tenant}/{session}_{ts}.jsonl，返回 (uri, bytes)。"""
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in (session_id or "default")
    )[:128]
    out_dir = Path(root) / "archives" / (tenant_id or "default")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{safe}_{ts}.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for m in messages:
            f.write(json.dumps(m, ensure_ascii=False) + "\n")
    uri = path.resolve().as_uri()
    return uri, path.stat().st_size


def record_archive_pointer(
    *,
    tenant_id: str,
    session_id: str,
    storage_uri: str,
    nbytes: int,
) -> bool:
    """写入 transcript_archives；失败仅打日志。"""
    try:
        import pymysql
        from pymysql.cursors import DictCursor

        from api.auth.mysql_conn import mysql_kwargs

        conn = pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO transcript_archives
                      (session_id, tenant_id, storage_uri, bytes)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (session_id, tenant_id, storage_uri, int(nbytes)),
                )
            conn.commit()
        finally:
            conn.close()
        return True
    except Exception as e:  # noqa: BLE001
        _log.debug("record_archive_pointer 失败: %s", e)
        return False


async def archive_and_clear_session(
    session_store: Any,
    *,
    project_root: Path,
    tenant_id: str,
    session_id: str,
) -> str | None:
    """导出全量消息 → 记指针 → clear_session。成功返回 uri。"""
    try:
        messages = await session_store.get_messages(session_id)
    except Exception as e:  # noqa: BLE001
        _log.warning("archive 读消息失败: %s", e)
        return None
    if not messages:
        await session_store.clear_session(session_id)
        return None
    uri, nbytes = archive_session_jsonl(
        messages,
        root=Path(project_root) / "data",
        tenant_id=tenant_id,
        session_id=session_id,
    )
    record_archive_pointer(
        tenant_id=tenant_id,
        session_id=session_id,
        storage_uri=uri,
        nbytes=nbytes,
    )
    await session_store.clear_session(session_id)
    return uri
