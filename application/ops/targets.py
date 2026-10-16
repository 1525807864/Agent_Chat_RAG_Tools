"""Ops Target 仓储：按租户隔离的客户项目 CRUD。"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Any

from application.ops.crypto import decrypt_secret, encrypt_secret
from application.tenancy import sanitize_tenant_id
from shared.timeutil import now_mysql


# 允许的类型（手写时勿拼错）
TARGET_TYPES = frozenset({"platform", "remote_agent", "dedicated_holmes"})


@dataclass(frozen=True)
class OpsTarget:
    """领域对象：给路由 / 执行器用。"""

    id: str
    tenant_id: str
    name: str
    target_type: str
    enabled: bool
    default_namespace: str | None
    endpoint_base: str | None
    # 下面两个是「解密后的明文」，仅进程内短时使用，禁止打日志、禁止进 JSON 响应
    auth_token: str | None
    kubeconfig: str | None
    notes: str | None
    created_by: str
    created_at: str
    updated_at: str
    # 仅列表展示：是否已配置凭证（不露内容）
    has_auth_token: bool = False
    has_kubeconfig: bool = False


def _connect():
    import pymysql
    from pymysql.cursors import DictCursor
    from api.auth.mysql_conn import mysql_kwargs

    return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)


def _new_id() -> str:
    """对外 ID：tgt_ + 16 字节 hex。"""
    return "tgt_" + secrets.token_hex(8)


def _row_to_target(row: dict[str, Any], *, reveal_secrets: bool) -> OpsTarget:
    """DB 行 → OpsTarget。reveal_secrets=False 时明文凭证恒为 None。"""
    token_enc = row.get("auth_token_enc")
    kube_enc = row.get("kubeconfig_enc")
    return OpsTarget(
        id=str(row["id"]),
        tenant_id=str(row["tenant_id"]),
        name=str(row["name"]),
        target_type=str(row["target_type"]),
        enabled=bool(int(row["enabled"])),
        default_namespace=(str(row["default_namespace"]) if row.get("default_namespace") else None),
        endpoint_base=(str(row["endpoint_base"]).rstrip("/") if row.get("endpoint_base") else None),
        auth_token=decrypt_secret(token_enc) if reveal_secrets else None,
        kubeconfig=decrypt_secret(kube_enc) if reveal_secrets else None,
        notes=(str(row["notes"]) if row.get("notes") else None),
        created_by=str(row.get("created_by") or ""),
        created_at=str(row.get("created_at") or ""),
        updated_at=str(row.get("updated_at") or ""),
        has_auth_token=bool(token_enc),
        has_kubeconfig=bool(kube_enc),
    )


def list_targets(tenant_id: str) -> list[OpsTarget]:
    """列出本租户全部目标（不含明文凭证）。"""
    tid = sanitize_tenant_id(tenant_id)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM ops_targets
                WHERE tenant_id=%s
                ORDER BY updated_at DESC
                """,
                (tid,),
            )
            rows = cur.fetchall() or []
    finally:
        conn.close()
    return [_row_to_target(r, reveal_secrets=False) for r in rows]


def get_target(tenant_id: str, target_id: str, *, for_exec: bool = False) -> OpsTarget | None:
    """按 id 取目标；for_exec=True 时解密凭证供执行器使用。"""
    tid = sanitize_tenant_id(tenant_id)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM ops_targets WHERE id=%s AND tenant_id=%s",
                (target_id, tid),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if not row:
        return None
    return _row_to_target(row, reveal_secrets=for_exec)


def create_target(
    *,
    tenant_id: str,
    name: str,
    target_type: str,
    created_by: str,
    endpoint_base: str | None = None,
    auth_token: str | None = None,
    kubeconfig: str | None = None,
    default_namespace: str | None = None,
    notes: str | None = None,
    enabled: bool = True,
) -> OpsTarget:
    """创建目标。"""
    tid = sanitize_tenant_id(tenant_id)
    ttype = (target_type or "").strip()
    if ttype not in TARGET_TYPES:
        raise ValueError(f"target_type 必须是 {sorted(TARGET_TYPES)}")
    nm = (name or "").strip()
    if not nm:
        raise ValueError("name 不能为空")
    # platform 不需要 endpoint；另外两种必须有
    base = (endpoint_base or "").strip().rstrip("/") or None
    if ttype in ("remote_agent", "dedicated_holmes") and not base:
        raise ValueError(f"{ttype} 必须提供 endpoint_base")

    tid_id = _new_id()
    now = now_mysql()
    conn = _connect()
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ops_targets (
                    id, tenant_id, name, target_type, enabled,
                    default_namespace, endpoint_base,
                    auth_token_enc, kubeconfig_enc, notes,
                    created_by, created_at, updated_at
                ) VALUES (
                    %s,%s,%s,%s,%s,
                    %s,%s,
                    %s,%s,%s,
                    %s,%s,%s
                )
                """,
                (
                    tid_id,
                    tid,
                    nm,
                    ttype,
                    1 if enabled else 0,
                    (default_namespace or "").strip() or None,
                    base,
                    encrypt_secret(auth_token),
                    encrypt_secret(kubeconfig),
                    (notes or "").strip() or None,
                    (created_by or "").strip(),
                    now,
                    now,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    out = get_target(tid, tid_id, for_exec=False)
    assert out is not None
    return out


def update_target(
    *,
    tenant_id: str,
    target_id: str,
    name: str | None = None,
    enabled: bool | None = None,
    endpoint_base: str | None = None,
    auth_token: str | None = None,
    kubeconfig: str | None = None,
    default_namespace: str | None = None,
    notes: str | None = None,
    clear_auth_token: bool = False,
    clear_kubeconfig: bool = False,
) -> OpsTarget:
    """更新；凭证字段：传入非空则覆盖；clear_*=True 则清空。"""
    tid = sanitize_tenant_id(tenant_id)
    existing = get_target(tid, target_id, for_exec=False)
    if existing is None:
        raise KeyError("target 不存在")

    conn = _connect()
    try:
        with conn.cursor() as cur:
            # 先读密文，便于「未传则保持」
            cur.execute(
                "SELECT auth_token_enc, kubeconfig_enc FROM ops_targets WHERE id=%s AND tenant_id=%s",
                (target_id, tid),
            )
            row = cur.fetchone() or {}
            token_enc = row.get("auth_token_enc")
            kube_enc = row.get("kubeconfig_enc")
            if clear_auth_token:
                token_enc = None
            elif auth_token is not None and str(auth_token).strip():
                token_enc = encrypt_secret(auth_token)
            if clear_kubeconfig:
                kube_enc = None
            elif kubeconfig is not None and str(kubeconfig).strip():
                kube_enc = encrypt_secret(kubeconfig)

            cur.execute(
                """
                UPDATE ops_targets SET
                    name=%s,
                    enabled=%s,
                    endpoint_base=%s,
                    default_namespace=%s,
                    notes=%s,
                    auth_token_enc=%s,
                    kubeconfig_enc=%s,
                    updated_at=%s
                WHERE id=%s AND tenant_id=%s
                """,
                (
                    (name if name is not None else existing.name).strip(),
                    (1 if enabled else 0) if enabled is not None else (1 if existing.enabled else 0),
                    (
                        (endpoint_base.strip().rstrip("/") if endpoint_base is not None else existing.endpoint_base)
                        or None
                    ),
                    (
                        default_namespace.strip()
                        if default_namespace is not None
                        else existing.default_namespace
                    )
                    or None,
                    (notes if notes is not None else existing.notes) or None,
                    token_enc,
                    kube_enc,
                    now_mysql(),
                    target_id,
                    tid,
                ),
            )
        conn.commit()
    finally:
        conn.close()
    out = get_target(tid, target_id, for_exec=False)
    assert out is not None
    return out


def delete_target(tenant_id: str, target_id: str) -> bool:
    """删除；返回是否删到行。"""
    tid = sanitize_tenant_id(tenant_id)
    conn = _connect()
    try:
        with conn.cursor() as cur:
            n = cur.execute(
                "DELETE FROM ops_targets WHERE id=%s AND tenant_id=%s",
                (target_id, tid),
            )
        conn.commit()
        return int(n or 0) > 0
    finally:
        conn.close()


def to_public_dict(t: OpsTarget) -> dict[str, Any]:
    """前端安全 DTO：无任何密文字段。"""
    return {
        "id": t.id,
        "tenantId": t.tenant_id,
        "name": t.name,
        "targetType": t.target_type,
        "enabled": t.enabled,
        "defaultNamespace": t.default_namespace,
        "endpointBase": t.endpoint_base,
        "hasAuthToken": t.has_auth_token,
        "hasKubeconfig": t.has_kubeconfig,
        "notes": t.notes,
        "createdBy": t.created_by,
        "createdAt": t.created_at,
        "updatedAt": t.updated_at,
    }