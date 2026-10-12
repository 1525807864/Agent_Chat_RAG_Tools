"""沙箱会话的领域模型。

设计
====
- 这是「一台电脑」的会话，不是 QA 专用结构。
- 垂直业务（qa / ops / office）只出现在 vertical + capabilities。
- 策略对齐用户/租户/会话三级，如：
    - 用户：允许 / 拒绝
    - 租户：允许 / 拒绝
    - 会话：允许 / 拒绝
- 时钟一律北京时间（shared.timeutil），与全站一致。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

# 平台承认的能力。新垂直只能从这里领工具，禁止私自 docker exec。
Capability = Literal["shell", "pwsh", "fs_read", "fs_write", "browser", "network"]

# 已接入或规划中的垂直；未知 vertical 一律拒绝发放会话。
Vertical = Literal["qa", "ops", "office", "generic"]
# 工作区写入策略
SandboxMode = Literal["read-only","workspace-write","full-in-container"]
# 出站网络策略
NetworkMode = Literal["deny","allowlist","open"]
# 高危命令审批策略
ApprovalPolicy = Literal["never","on-risky","always"]
# 执行种类：命令+文件工具(sandbox-as-Tools)
ExecKind = Literal["shell","pwsh","fs_read","fs_write","fs_list"]

@dataclass
class SandboxLimits:
    """单会话硬限制。Broker 在创建容器时落到 docker 参数。"""

    memory: str = "1g"
    cpus: str = "1"
    pids: int = 256
    exec_timeout_sec: int = 30
    max_output_bytes: int = 65536
    idle_sec: int = 1800

@dataclass 
class SandboxPolicySnapshot:
    """会话创建时固化的策略快照"""
    mode: str = "workspace-write"
    network_mode: str = "deny"
    approval: str = "on-risky"
    egress_allowlist: tuple[str,...] = ()
    allow_shell_string: bool = False 


@dataclass
class SandboxSession:
    """一次租户级沙箱租约。

    container_id:
        运行时句柄（docker 容器名/ID）。禁止回传给前端。
    workspace_host:
        宿主机上该会话的工作区；容器内固定挂到 /workspace。
    """

    id: str
    tenant_id: str
    vertical: str
    capabilities: frozenset[str]
    container_id: str
    workspace_host: str
    created_at: str
    last_active_at: str
    limits: SandboxLimits = field(default_factory=SandboxLimits)
    policy: SandboxPolicySnapshot = field(default_factory=SandboxPolicySnapshot)
    status: str = "running"  # running | released | error
    meta: dict[str, Any] = field(default_factory=dict)

    def allow(self, cap: str) -> bool:
        return cap in self.capabilities


@dataclass
class ExecRequest:
    """
    在已有会话里执行一条命令。
    argv:
        优先纯参数列表。shell 字符串仅当 policy.allow_shell_string=True。
    path / content:
        文件工具使用；命令工具忽略。
    approved:
        调用方已通过人工审批时为 True，跳过二次拦截。
    """

    session_id: str
    tenant_id: str
    kind: ExecKind
    argv: list[str] = field(default_factory=list)
    cwd: str = "/workspace"
    timeout_sec: int | None = None
    path: str = ""
    content: str = ""
    approved: bool = False


@dataclass
class ExecResult:
    """工具结果。文件读也复用 stdout 字段，便于 Agent 统一解析。"""

    ok: bool
    exit_code: int
    stdout: str
    stderr: str
    truncated: bool
    duration_ms: int
    timed_out: bool = False
    needs_approval: bool = False 
    risk_reason: str = ""
    