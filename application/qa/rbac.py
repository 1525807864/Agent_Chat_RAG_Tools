"""测试平台 RBAC。

权限矩阵（产品约定）：
- admin   : 读写项目/用例、执行、管理成员
- execute : 只读 + 执行（冒烟 / UI Agent）；禁止编辑用例
- view    : 只读

成员名单存在租户 data/qa/<tenant>/members.json。
租户内「第一次」访问 QA 的登录用户自动写成 admin（SaaS 开户）。
之后其他人必须由 admin 邀请，否则 403。
"""

from __future__ import annotations

from fastapi import Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
from domain.qa import ALLOWED_ROLES, ROLE_ADMIN, ROLE_EXECUTE, ROLE_VIEW, QaMember
from infrastructure.qa.filesystem import QaFileStore, _sid

# 动作 → 允许的角色。读接口不走这里，只要求「是本租户成员」。
PERMISSIONS: dict[str, frozenset[str]] = {
    "project:write": frozenset({ROLE_ADMIN}),
    "project:delete": frozenset({ROLE_ADMIN}),
    "case:write": frozenset({ROLE_ADMIN}),  # 生成 / 确认 / 删除 / 助手改稿
    "run:execute": frozenset({ROLE_ADMIN, ROLE_EXECUTE}),
    "member:manage": frozenset({ROLE_ADMIN}),
}


def _store(tenant_id: str) -> QaFileStore:
    return QaFileStore(tenant_id)


def bootstrap_owner(
    tenant_id: str,
    user_id: str,
    *,
    store: QaFileStore | None = None,
) -> list[QaMember]:
    """成员表为空时，把当前登录用户写成租户 owner（admin）。

    这是 SaaS「首次登录 = 团队管理员」的入口，只发生一次。
    store 可选，单测可注入临时目录。
    """
    fs = store or _store(tenant_id)
    members = fs.list_members()
    # 去掉旧壳数据：id=me 且没有绑定登录账号
    real = [m for m in members if (m.user_id or "").strip()]
    if real:
        # 若盘上还有无 user_id 的脏数据，落盘清洗一次
        if len(real) != len(members):
            fs.save_members(real)
        return real
    owner = QaMember(
        id=_sid(),
        name=user_id,
        role=ROLE_ADMIN,
        user_id=user_id,
    )
    fs.save_members([owner])
    return [owner]


def resolve_member(
    tenant_id: str,
    user_id: str,
    *,
    store: QaFileStore | None = None,
) -> QaMember | None:
    """按登录 user_id 找本租户成员；找不到返回 None。"""
    for m in bootstrap_owner(tenant_id, user_id, store=store):
        if m.user_id == user_id:
            return m
    return None


def require_member(user: AuthUser) -> QaMember:
    """必须是本租户 QA 成员。首次访问会 bootstrap 成 admin。"""
    member = resolve_member(user.tenant_id, user.user_id)
    if member is None:
        raise HTTPException(
            status_code=403,
            detail="你不在该租户的测试平台成员名单中，请联系管理员邀请",
        )
    if member.role not in ALLOWED_ROLES:
        raise HTTPException(status_code=403, detail="非法角色")
    return member


def require_qa_perm(action: str):
    """FastAPI 依赖工厂：校验动作权限。

    用法::
        user: AuthUser = Depends(require_qa_perm("run:execute"))
    """

    async def _dep(user: AuthUser = Depends(get_current_user)) -> AuthUser:
        member = require_member(user)
        allowed = PERMISSIONS.get(action)
        if allowed is None:
            raise HTTPException(status_code=500, detail=f"未知权限动作: {action}")
        if member.role not in allowed:
            raise HTTPException(status_code=403, detail="权限不足")
        return user

    return _dep


def me_payload(user: AuthUser) -> dict:
    """给前端的当前身份，用来藏按钮。不能替代服务端校验。"""
    member = require_member(user)
    role = member.role
    return {
        "userId": user.user_id,
        "tenantId": user.tenant_id,
        "role": role,
        "permissions": {
            "canWriteProject": role == ROLE_ADMIN,
            "canWriteCase": role == ROLE_ADMIN,
            "canExecute": role in {ROLE_ADMIN, ROLE_EXECUTE},
            "canManageMembers": role == ROLE_ADMIN,
        },
    }
