"""沙箱运行时协议。Docker 是第一种实现；以后可换 Firecracker / 云桌面。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from infrastructure.sandbox.models import (
    ExecRequest,
    ExecResult,
    SandboxLimits,
    SandboxSession,
)


class SandboxRuntime(ABC):
    """隔离计算环境的生命周期与命令执行。"""

    @abstractmethod
    async def create(
        self,
        *,
        session_id: str,
        tenant_id: str,
        caps: frozenset[str],
        limits: SandboxLimits,
        workspace_host: str,
        network: str,
        proxy_url: str = "",
    ) -> str:
        """创建隔离环境，返回 container_id（勿回传给前端）。"""

    @abstractmethod
    async def exec(
        self,
        session: SandboxSession,
        req: ExecRequest,
        *,
        allow_shell_string: bool = False,
    ) -> ExecResult:
        """在会话内执行 argv。超时必须杀掉该次 exec。"""

    @abstractmethod
    async def destroy(self, session: SandboxSession) -> None:
        """幂等销毁。"""
