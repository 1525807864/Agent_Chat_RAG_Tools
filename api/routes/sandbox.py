"""平台沙箱 HTTP。垂直产品可走 LangChain 工具，也可走本 API 做运维探活。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth.deps import AuthUser, get_current_user
from application.sandbox.service import SandboxApplication
from infrastructure.sandbox.models import ExecResult
from shared.errors import AppError

router = APIRouter(prefix="/api/sandbox", tags=["sandbox"])


class AcquireBody(BaseModel):
    vertical: str = Field(default="generic", max_length=32)


class ExecBody(BaseModel):
    """兼容旧接口：单字符串命令。"""

    command: str = Field(..., min_length=1, max_length=4000)
    approved: bool = False


class ArgvBody(BaseModel):
    argv: list[str] = Field(..., min_length=1, max_length=64)
    approved: bool = False


class PathBody(BaseModel):
    path: str = Field(default="/workspace", max_length=512)


class FsWriteBody(BaseModel):
    path: str = Field(..., max_length=512)
    content: str = Field(..., max_length=200_000)


def _app(user: AuthUser) -> SandboxApplication:
    return SandboxApplication(user.tenant_id)


def _http(exc: AppError) -> HTTPException:
    detail: dict | str = exc.message
    if exc.extras:
        detail = {"message": exc.message, "code": exc.code.value, **exc.extras}
    return HTTPException(status_code=exc.http_status, detail=detail)


def _exec_out(r: ExecResult) -> dict:
    return {
        "ok": r.ok,
        "exitCode": r.exit_code,
        "stdout": r.stdout,
        "stderr": r.stderr,
        "truncated": r.truncated,
        "durationMs": r.duration_ms,
        "timedOut": r.timed_out,
        "needsApproval": r.needs_approval,
        "riskReason": r.risk_reason,
    }


@router.post("/sessions")
async def acquire(body: AcquireBody, user: AuthUser = Depends(get_current_user)):
    try:
        s = await _app(user).acquire(body.vertical)
    except AppError as exc:
        raise _http(exc) from exc
    return {
        "id": s.id,
        "vertical": s.vertical,
        "capabilities": sorted(s.capabilities),
        "createdAt": s.created_at,
        "status": s.status,
        "policy": {
            "mode": s.policy.mode,
            "networkMode": s.policy.network_mode,
            "approval": s.policy.approval,
        },
    }


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, user: AuthUser = Depends(get_current_user)):
    try:
        return _app(user).session_public(session_id)
    except AppError as exc:
        raise _http(exc) from exc


@router.post("/sessions/{session_id}/shell")
async def shell(
    session_id: str,
    body: ExecBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).shell(
            session_id, body.command, approved=body.approved
        )
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.post("/sessions/{session_id}/pwsh")
async def pwsh(
    session_id: str,
    body: ExecBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).pwsh(
            session_id, body.command, approved=body.approved
        )
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.post("/sessions/{session_id}/exec")
async def exec_argv(
    session_id: str,
    body: ArgvBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).exec_argv(
            session_id, "shell", body.argv, approved=body.approved
        )
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.post("/sessions/{session_id}/fs/read")
async def fs_read(
    session_id: str,
    body: PathBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).read_file(session_id, body.path)
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.post("/sessions/{session_id}/fs/write")
async def fs_write(
    session_id: str,
    body: FsWriteBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).write_file(session_id, body.path, body.content)
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.post("/sessions/{session_id}/fs/list")
async def fs_list(
    session_id: str,
    body: PathBody,
    user: AuthUser = Depends(get_current_user),
):
    try:
        r = await _app(user).list_dir(session_id, body.path)
    except AppError as exc:
        raise _http(exc) from exc
    return _exec_out(r)


@router.delete("/sessions/{session_id}")
async def release(session_id: str, user: AuthUser = Depends(get_current_user)):
    try:
        await _app(user).release(session_id)
    except AppError as exc:
        raise _http(exc) from exc
    return {"ok": True}
