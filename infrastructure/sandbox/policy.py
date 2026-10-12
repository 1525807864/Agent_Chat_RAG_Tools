"""垂直能力策略：谁能开什么工具。


安全模型（对齐 Claude Code / Codex）
====================================
1. Capability：垂直默认能用哪些工具（默认拒绝）。
2. Mode：工作区可写范围（read-only / workspace-write）。
3. Network：deny | allowlist(代理) | open。
4. Approval：高危命令是否要人确认 —— 与内核/容器强制隔离是两层。
Permission（本模块）决定「能不能发这次调用」；
Runtime（docker + egress proxy）决定「跑起来能碰什么」。
"""

from __future__ import annotations
from config.settings import get_settings 
from infrastructure.sandbox.models import SandboxPolicySnapshot
# 每个垂直的默认能力。产品扩垂直时只改这一张表。
_DEFAULT: dict[str, frozenset[str]] = {
    "generic": frozenset({"shell", "fs_read"}),
    "qa": frozenset({"shell", "fs_read", "browser"}),
    "ops": frozenset({"shell", "pwsh", "fs_read", "fs_write"}),
    "office": frozenset({"shell", "fs_read", "fs_write"}),
}
# fs_list 与 fs_read 共用读能力，不单独发 cap


# 绝对不会发给任何垂直的能力（平台级封死，预留）。
_FORBIDDEN: frozenset[str] = frozenset()


def resolve_capabilities(
    vertical: str,
    extra: frozenset[str] | None = None,
) -> frozenset[str]:
    """合并默认能力与调用方申请；未知 vertical 抛 ValueError。"""
    key = (vertical or "").strip().lower() or "generic"
    if key not in _DEFAULT:
        raise ValueError(f"未知垂直: {key}")
    wanted = set(_DEFAULT[key])
    if extra:
        wanted |= set(extra)
    if "browser" in wanted:
        wanted.add("network")
    wanted -= set(_FORBIDDEN)
    return frozenset(wanted)

def build_policy_snapshot()->SandboxPolicySnapshot:
    """从Settings固化本会话策略。"""
    s = get_settings()
    allow = tuple(
        p.strip().lower()
        for p in (s.sandbox_egress_allowlist or "").split(",")
        if p.strip()
    )
    return SandboxPolicySnapshot(
        mode = s.sandbox_mode,
        network_mode = s.sandbox_network_mode,
        approval = s.sandbox_approval,
        egress_allowlist = allow,
        allow_shell_string = bool(s.sandbox_allow_shell_string),
    )

def need_proxy_network(policy: SandboxPolicySnapshot,caps: frozenset[str])->bool:
    """是否需要把容器接入egress代理网"""
    if policy.network_mode == "deny":
        return False 
    if policy.network_mode == "open":
        return True 
    return "network" in caps or "browser" in caps

def need_network(caps: frozenset[str]) -> bool:
    """浏览器或显式 network 才接通网桥；默认 none 断网。"""
    return "network" in caps or "browser" in caps


def assert_exec_kind(caps: frozenset[str], kind: str) -> None:
    """执行前校验会话是否拥有对应能力。"""
    mapping = {
        "shell": "shell",
        "pwsh": "pwsh",
        "fs_read": "fs_read",
        "fs_list": "fs_read",  # 列目录归读能力
        "fs_write": "fs_write",
    }
    need = mapping.get(kind)
    if not need:
        raise PermissionError(f"未知执行种类: {kind}")
    if need not in caps:
        raise PermissionError(f"本会话未授予 {need}")

def assert_mode_allows_write(policy: SandboxPolicySnapshot, kind: str) -> None:
    """read-only 会话禁止写文件与改盘命令以外的写工具。"""
    if kind == "fs_write" and policy.mode == "read-only":
        raise PermissionError("会话为 read-only，禁止写入")