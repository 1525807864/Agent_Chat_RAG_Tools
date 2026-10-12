"""Sandbox-as-Tools：细粒度工具面（对齐 Codex / Computer Use）。

垂直 Agent 只 bind 本模块，不感知 Docker / 代理。
"""

from __future__ import annotations

from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import BaseModel, Field

from infrastructure.sandbox.broker import SandboxBroker
from infrastructure.sandbox.models import ExecRequest, ExecResult
from shared.errors import AppError


class _ShellArgs(BaseModel):
    argv: list[str] = Field(
        ..., min_length=1, description='纯 argv，例如 ["ls","-la"]'
    )


class _PwshArgs(BaseModel):
    argv: list[str] = Field(..., min_length=1, description="pwsh 参数列表")


class _PathArgs(BaseModel):
    path: str = Field(
        default="/workspace", max_length=512, description="/workspace 下路径"
    )


class _WriteArgs(BaseModel):
    path: str = Field(..., max_length=512)
    content: str = Field(..., max_length=200_000)


def sandbox_tools(
    broker: SandboxBroker,
    *,
    session_id: str,
    tenant_id: str,
) -> list[Any]:
    """为指定会话构造工具列表。"""

    async def _shell(argv: list[str]) -> str:
        return await _run(
            broker,
            ExecRequest(
                session_id=session_id,
                tenant_id=tenant_id,
                kind="shell",
                argv=argv,
            ),
        )

    async def _pwsh(argv: list[str]) -> str:
        return await _run(
            broker,
            ExecRequest(
                session_id=session_id,
                tenant_id=tenant_id,
                kind="pwsh",
                argv=argv,
            ),
        )

    async def _list(path: str = "/workspace") -> str:
        return await _run(
            broker,
            ExecRequest(
                session_id=session_id,
                tenant_id=tenant_id,
                kind="fs_list",
                path=path,
            ),
        )

    async def _read(path: str) -> str:
        return await _run(
            broker,
            ExecRequest(
                session_id=session_id,
                tenant_id=tenant_id,
                kind="fs_read",
                path=path,
            ),
        )

    async def _write(path: str, content: str) -> str:
        return await _run(
            broker,
            ExecRequest(
                session_id=session_id,
                tenant_id=tenant_id,
                kind="fs_write",
                path=path,
                content=content,
            ),
        )

    return [
        StructuredTool.from_function(
            name="sandbox_bash",
            description="在沙箱内执行命令（argv 数组，默认无 shell 管道）。工作目录 /workspace。",
            coroutine=_shell,
            args_schema=_ShellArgs,
        ),
        StructuredTool.from_function(
            name="sandbox_pwsh",
            description="在沙箱内执行 PowerShell Core（argv）。",
            coroutine=_pwsh,
            args_schema=_PwshArgs,
        ),
        StructuredTool.from_function(
            name="sandbox_list_dir",
            description="列出沙箱 /workspace 下目录。",
            coroutine=_list,
            args_schema=_PathArgs,
        ),
        StructuredTool.from_function(
            name="sandbox_read_file",
            description="读取沙箱工作区内文件。",
            coroutine=_read,
            args_schema=_PathArgs,
        ),
        StructuredTool.from_function(
            name="sandbox_write_file",
            description="写入沙箱工作区文件（需 fs_write 且非 read-only）。",
            coroutine=_write,
            args_schema=_WriteArgs,
        ),
    ]


async def _run(broker: SandboxBroker, req: ExecRequest) -> str: # 执行请求，返回结果
    try:
        return _fmt(await broker.exec(req))
    except AppError as exc:
        if exc.code.value == "SANDBOX_APPROVAL_REQUIRED":
            return f"[needs_approval] {exc.message}"
        return f"[error] {exc.message}"


def _fmt(r: ExecResult) -> str: # 格式化结果，用于返回给Agent
    if r.needs_approval:
        return f"[needs_approval] {r.risk_reason}"
    flag = "timeout" if r.timed_out else ("ok" if r.ok else "fail")
    body = (r.stdout or "") + (("\n" + r.stderr) if r.stderr else "")
    return f"[{flag} exit={r.exit_code} {r.duration_ms}ms]\n{body}"
