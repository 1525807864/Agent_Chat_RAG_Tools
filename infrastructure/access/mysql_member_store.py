"""MemberStorePort 的 MySQL 适配器。"""

from __future__ import annotations

from typing import Optional

from domain.access import ROLE_OWNER, TenantMember
from domain.ports import MemberStorePort


class MysqlMemberStore(MemberStorePort):
    """读写 tenant_members 表。"""

    def _connect(self):
        import pymysql
        from pymysql.cursors import DictCursor

        from api.auth.mysql_conn import mysql_kwargs

        return pymysql.connect(**mysql_kwargs(), cursorclass=DictCursor)

    def get(self, tenant_id: str, user_id: str) -> Optional[TenantMember]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id, user_id, role, status
                    FROM tenant_members
                    WHERE tenant_id=%s AND user_id=%s
                    """,
                    (tenant_id, user_id),
                )
                row = cur.fetchone()
            if not row:
                return None
            return TenantMember(
                tenant_id=row["tenant_id"],
                user_id=row["user_id"],
                role=row["role"],
                status=row["status"],
            )
        finally:
            conn.close()

    def upsert(
        self, member: TenantMember, *, invited_by: str | None = None
    ) -> None:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO tenant_members
                      (tenant_id, user_id, role, status, invited_by)
                    VALUES (%s,%s,%s,%s,%s)
                    ON DUPLICATE KEY UPDATE
                      role=VALUES(role),
                      status=VALUES(status)
                    """,
                    (
                        member.tenant_id,
                        member.user_id,
                        member.role,
                        member.status,
                        invited_by,
                    ),
                )
            conn.commit()
        finally:
            conn.close()

    def list_members(self, tenant_id: str) -> list[TenantMember]:
        conn = self._connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT tenant_id, user_id, role, status
                    FROM tenant_members WHERE tenant_id=%s
                    """,
                    (tenant_id,),
                )
                rows = cur.fetchall() or []
            return [
                TenantMember(
                    tenant_id=r["tenant_id"],
                    user_id=r["user_id"],
                    role=r["role"],
                    status=r["status"],
                )
                for r in rows
            ]
        finally:
            conn.close()

    def ensure_owner(self, tenant_id: str, user_id: str) -> TenantMember:
        existing = self.list_members(tenant_id)
        if existing:
            mine = next((m for m in existing if m.user_id == user_id), None)
            if mine:
                return mine
            raise ValueError("租户已初始化，请联系管理员邀请")
        owner = TenantMember(
            tenant_id=tenant_id, user_id=user_id, role=ROLE_OWNER
        )
        self.upsert(owner, invited_by=None)
        return owner
