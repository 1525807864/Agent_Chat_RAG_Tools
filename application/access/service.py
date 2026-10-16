"""租户成员解析与权限判定（应用层）。

边界：
- 不 import FastAPI / HTTPException
- 持久化只依赖 MemberStorePort
- 路由层把 AccessError.code 映射成 HTTP 状态码
"""

from __future__ import annotations

from dataclasses import dataclass

from domain.access import TenantMember, permissions_for_role
from domain.ports import MemberStorePort


class AccessError(Exception):
    """应用层访问失败。"""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        # forbidden | not_member | inactive
        self.code = code
        self.message = message


@dataclass(frozen=True)
class MeResult:
    """当前用户在本租户的身份快照（给 /api/me）。"""

    user_id: str
    tenant_id: str
    role: str
    permissions: dict[str, bool]


class AccessService:
    """访问控制用例编排。"""

    def __init__(self, members: MemberStorePort) -> None:
        self._members = members

    def resolve_member(self, tenant_id: str, user_id: str) -> TenantMember:
        m = self._members.get(tenant_id, user_id)
        if m is None:
            raise AccessError("not_member", "你不在该租户成员名单中")
        if not m.is_active():
            raise AccessError("inactive", "成员已停用或角色非法")
        return m

    def require(self, tenant_id: str, user_id: str, action: str) -> TenantMember:
        """校验动作权限；失败抛 AccessError。"""
        m = self.resolve_member(tenant_id, user_id)
        if not m.can(action):
            raise AccessError("forbidden", "权限不足")
        return m

    def me(self, tenant_id: str, user_id: str) -> MeResult:
        m = self.resolve_member(tenant_id, user_id)
        return MeResult(
            user_id=user_id,
            tenant_id=tenant_id,
            role=m.role,
            permissions=permissions_for_role(m.role),
        )

    def bootstrap_owner_on_register(
        self, tenant_id: str, user_id: str
    ) -> TenantMember:
        """注册成功后：该用户成为自己租户的 owner。

        生产环境不要在「任意首次访问业务接口」时自动升权。
        """
        return self._members.ensure_owner(tenant_id, user_id)

    def maybe_bootstrap_owner_on_login(
        self, tenant_id: str, user_id: str
    ) -> TenantMember | None:
        """登录后：仅当本租户尚无任何成员时，把当前用户写成 owner。

        用于旧库迁移（users 表已有人、tenant_members 为空）。
        租户已有成员且当前用户不在名单 → 返回 None（业务接口会 403）。
        """
        existing = self._members.get(tenant_id, user_id)
        if existing is not None:
            return existing
        if self._members.list_members(tenant_id):
            return None
        return self._members.ensure_owner(tenant_id, user_id)
