"""
租户访问控制：角色与权限矩阵
"""
from __future__ import annotations
from dataclasses import dataclass
# ---------- 平台角色（租户内）----------
ROLE_OWNER = "owner"          # 开户人：成员管理 + 全部写
ROLE_ADMIN = "admin"          # 管理写：知识库 / 成员（不含移交 owner）
ROLE_MEMBER = "member"        # 日常使用：对话、建库、跑 QA
ROLE_VIEWER = "viewer"        # 只读
ROLE_OPS = "ops_operator"     # 运维排障 / 终端等高危能力
ALLOWED_ROLES = frozenset(
    {ROLE_OWNER, ROLE_ADMIN, ROLE_MEMBER, ROLE_VIEWER, ROLE_OPS}
)
# ---------- 动作（路由 require_perm 用这些字面量）----------
PERM_CHAT_USE = "chat:use"
PERM_SESSION_READ = "session:read"
PERM_SESSION_WRITE = "session:write"
PERM_KB_READ = "knowledge:read"
PERM_KB_WRITE = "knowledge:write"       # 上传 / 同步或异步建库
PERM_OPS_ASK = "ops:ask"
PERM_OPS_TERMINAL = "ops:terminal"
PERM_SANDBOX_EXEC = "sandbox:exec"
PERM_BILLING_READ = "billing:read"
PERM_BILLING_ADMIN = "billing:admin"    # flush 等
PERM_MEMBER_MANAGE = "member:manage"
PERM_QA_WRITE = "qa:write"
PERM_QA_EXECUTE = "qa:execute"
# 角色 → 允许的动作集合（默认拒绝：不在集合里就是禁止）
_ROLE_PERMS: dict[str, frozenset[str]] = {
    ROLE_OWNER: frozenset(
        {
            PERM_CHAT_USE,
            PERM_SESSION_READ,
            PERM_SESSION_WRITE,
            PERM_KB_READ,
            PERM_KB_WRITE,
            PERM_OPS_ASK,
            PERM_OPS_TERMINAL,
            PERM_SANDBOX_EXEC,
            PERM_BILLING_READ,
            PERM_BILLING_ADMIN,
            PERM_MEMBER_MANAGE,
            PERM_QA_WRITE,
            PERM_QA_EXECUTE,
        }
    ),
    ROLE_ADMIN: frozenset(
        {
            PERM_CHAT_USE,
            PERM_SESSION_READ,
            PERM_SESSION_WRITE,
            PERM_KB_READ,
            PERM_KB_WRITE,
            PERM_OPS_ASK,
            PERM_OPS_TERMINAL,
            PERM_SANDBOX_EXEC,
            PERM_BILLING_READ,
            PERM_MEMBER_MANAGE,
            PERM_QA_WRITE,
            PERM_QA_EXECUTE,
        }
    ),
    ROLE_MEMBER: frozenset(
        {
            PERM_CHAT_USE,
            PERM_SESSION_READ,
            PERM_SESSION_WRITE,
            PERM_KB_READ,
            PERM_KB_WRITE,
            PERM_BILLING_READ,
            PERM_QA_WRITE,
            PERM_QA_EXECUTE,
        }
    ),
    ROLE_OPS: frozenset(
        {
            PERM_CHAT_USE,
            PERM_SESSION_READ,
            PERM_KB_READ,
            PERM_OPS_ASK,
            PERM_OPS_TERMINAL,
            PERM_SANDBOX_EXEC,
            PERM_BILLING_READ,
        }
    ),
    ROLE_VIEWER: frozenset(
        {
            PERM_CHAT_USE,       # 若产品要求 viewer 不能聊，删掉本项
            PERM_SESSION_READ,
            PERM_KB_READ,
            PERM_BILLING_READ,
        }
    ),
}
@dataclass(frozen=True)
class TenantMember:
    """租户成员实体（聚合内身份，不是jwt）"""
    tenant_id: str 
    user_id: str 
    role: str 
    status: str = "active"
    
    def is_active(self)->bool:
        return self.status == "active" and self.role in ALLOWED_ROLES
    def can(self, action: str) -> bool:
        """领域判定：当前角色是否拥有动作。"""
        if not self.is_active():
            return False
        return action in _ROLE_PERMS.get(self.role, frozenset())

def permissions_for_role(role:str)->dict[str,bool]:
    """给前端藏按钮用的布尔包，不能替代服务器can()"""
    m = TenantMember(tenant_id="_",user_id="_",role=role)
    return {
        "canChat": m.can(PERM_CHAT_USE),
        "canWriteKnowledge": m.can(PERM_KB_WRITE),
        "canAskOps": m.can(PERM_OPS_ASK),
        "canOpenTerminal": m.can(PERM_OPS_TERMINAL),
        "canExecSandbox": m.can(PERM_SANDBOX_EXEC),
        "canManageMembers": m.can(PERM_MEMBER_MANAGE),
        "canWriteQa": m.can(PERM_QA_WRITE),
        "canExecuteQa": m.can(PERM_QA_EXECUTE),
        "canAdminBilling": m.can(PERM_BILLING_ADMIN),
    }
