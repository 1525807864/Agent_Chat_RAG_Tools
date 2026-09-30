"""P2：精选记忆 memory_items（与 memdir JSON 双写）。"""

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


def upsert_memory_item(
    *,
    tenant_id: str,
    session_id: str | None,
    kind: str,
    text: str,
    origin: str = "agent",
    tags: list[str] | None = None,
    score_hint: float = 0.5,
    meta: dict | None = None,
    item_id: str | None = None,
) -> str | None:
    """写入/更新一条记忆；失败返回 None。"""
    iid = item_id or uuid.uuid4().hex
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_items
                      (id, tenant_id, session_id, kind, text, origin,
                       tags_json, meta_json, score_hint)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      text=VALUES(text),
                      origin=VALUES(origin),
                      tags_json=VALUES(tags_json),
                      meta_json=VALUES(meta_json),
                      score_hint=VALUES(score_hint),
                      kind=VALUES(kind)
                    """,
                    (
                        iid,
                        tenant_id or "default",
                        session_id,
                        kind,
                        text or "",
                        origin,
                        json.dumps(tags or [], ensure_ascii=False),
                        json.dumps(meta or {}, ensure_ascii=False),
                        float(score_hint),
                    ),
                )
            conn.commit()
        finally:
            conn.close()
        return iid
    except Exception as e:  # noqa: BLE001
        _log.debug("upsert_memory_item 失败: %s", e)
        return None


def list_session_items(
    *, tenant_id: str, session_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    try:
        conn = _connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, kind, text, origin, tags_json, meta_json,
                           score_hint, created_at, updated_at
                    FROM memory_items
                    WHERE tenant_id=%s AND session_id=%s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (tenant_id, session_id, int(limit)),
                )
                rows = cur.fetchall() or []
            out: list[dict[str, Any]] = []
            for r in rows:
                tags = r.get("tags_json")
                meta = r.get("meta_json")
                if isinstance(tags, str):
                    try:
                        tags = json.loads(tags)
                    except Exception:  # noqa: BLE001
                        tags = []
                if isinstance(meta, str):
                    try:
                        meta = json.loads(meta)
                    except Exception:  # noqa: BLE001
                        meta = {}
                out.append(
                    {
                        "id": r["id"],
                        "kind": r["kind"],
                        "text": r["text"],
                        "origin": r.get("origin") or "agent",
                        "tags": tags or [],
                        "meta": meta or {},
                        "score_hint": float(r.get("score_hint") or 0.5),
                    }
                )
            return out
        finally:
            conn.close()
    except Exception as e:  # noqa: BLE001
        _log.debug("list_session_items 失败: %s", e)
        return []
