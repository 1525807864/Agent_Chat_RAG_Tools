"""进程内成员表：AUTH_BACKEND=sqlite 等本地场景，不依赖 MySQL。"""

from __future__ import annotations

from threading import Lock
from typing import Optional

from domain.access import ROLE_OWNER, TenantMember
from domain.ports import MemberStorePort


class MemoryMemberStore(MemberStorePort):
    """线程安全的内存实现；进程重启后需重新 bootstrap。"""

    def __init__(self) -> None:
        self._lock = Lock()
        # key = (tenant_id, user_id)
        self._rows: dict[tuple[str, str], TenantMember] = {}

    def get(self, tenant_id: str, user_id: str) -> Optional[TenantMember]:
        with self._lock:
            return self._rows.get((tenant_id, user_id))

    def upsert(
        self, member: TenantMember, *, invited_by: str | None = None
    ) -> None:
        _ = invited_by
        with self._lock:
            self._rows[(member.tenant_id, member.user_id)] = member

    def list_members(self, tenant_id: str) -> list[TenantMember]:
        with self._lock:
            return [m for (t, _), m in self._rows.items() if t == tenant_id]

    def ensure_owner(self, tenant_id: str, user_id: str) -> TenantMember:
        with self._lock:
            existing = [m for (t, _), m in self._rows.items() if t == tenant_id]
            if existing:
                mine = next((m for m in existing if m.user_id == user_id), None)
                if mine:
                    return mine
                raise ValueError("租户已初始化，请联系管理员邀请")
            owner = TenantMember(
                tenant_id=tenant_id, user_id=user_id, role=ROLE_OWNER
            )
            self._rows[(tenant_id, user_id)] = owner
            return owner
