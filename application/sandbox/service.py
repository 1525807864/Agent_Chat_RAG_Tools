"""应用门面：路由 / 垂直 Agent 只依赖本类，不直接碰 Docker。"""

from __future__ import annotations

from typing import Any

from infrastructure.sandbox.broker import get_sandbox_broker
from infrastructure.sandbox.models import ExecKind, ExecRequest, ExecResult, SandboxSession


class SandboxApplication:
    """租户级沙箱门面。"""

    def __init__(self, tenant_id: str) -> None:
        self._tenant = tenant_id
        self._broker = get_sandbox_broker()

    async def acquire(self, vertical: str = "generic") -> SandboxSession:
        return await self._broker.acquire(
            tenant_id=self._tenant,
            vertical=vertical,
        )

    async def shell(
        self, session_id: str, command: str, *, approved: bool = False
    ) -> ExecResult:
        """兼容旧 API：单字符串命令（受 allow_shell_string / 审批约束）。"""
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind="shell",
                argv=[command],
                approved=approved,
            )
        )

    async def pwsh(
        self, session_id: str, command: str, *, approved: bool = False
    ) -> ExecResult:
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind="pwsh",
                argv=[command],
                approved=approved,
            )
        )

    async def exec_argv(
        self,
        session_id: str,
        kind: ExecKind,
        argv: list[str],
        *,
        approved: bool = False,
    ) -> ExecResult:
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind=kind,
                argv=argv,
                approved=approved,
            )
        )

    async def read_file(self, session_id: str, path: str) -> ExecResult:
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind="fs_read",
                path=path,
            )
        )

    async def write_file(
        self, session_id: str, path: str, content: str
    ) -> ExecResult:
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind="fs_write",
                path=path,
                content=content,
            )
        )

    async def list_dir(
        self, session_id: str, path: str = "/workspace"
    ) -> ExecResult:
        return await self._broker.exec(
            ExecRequest(
                session_id=session_id,
                tenant_id=self._tenant,
                kind="fs_list",
                path=path,
            )
        )

    async def release(self, session_id: str) -> None:
        await self._broker.release(
            session_id=session_id,
            tenant_id=self._tenant,
        )

    def session_public(self, session_id: str) -> dict[str, Any]:
        return self._broker.get_public(session_id, self._tenant)
