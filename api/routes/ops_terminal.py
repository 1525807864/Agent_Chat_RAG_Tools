"""Ops 交互终端 HTTP 门面（P1 + P2）。

流程
====
POST /api/ops/terminal/sessions
  → acquire ops 沙箱（若未传 sessionId）
  → 若 SANDBOX_APPROVAL 需要且未 approved → 409
  → TtydManager.open
  → 返回 terminalUrl（同源 proxy 路径）

GET/DELETE /api/ops/terminal/sessions/{terminalId}

GET  /api/ops/terminal/view?ticket=...   （本机调试 302，生产勿用）

P2 同源反代：
  HTTP  /api/ops/terminal/proxy/{ticket}/...
  WS    /api/ops/terminal/proxy/{ticket}/ws
  ttyd 以 --base-path 与上述前缀对齐，页面内资源/WS 路径正确。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import RedirectResponse, Response
from pydantic import BaseModel, Field

from api.auth.access_deps import require_perm
from api.auth.deps import AuthUser, get_current_user
from application.ops.rbac import can_open_terminal
from domain.access import PERM_OPS_TERMINAL
from application.ops.ttyd_manager import get_ttyd_manager
from application.sandbox.service import SandboxApplication
from config.settings import get_settings
from shared.errors import AppError

_log = logging.getLogger("nexora.ops.terminal")

router = APIRouter(prefix="/api/ops/terminal", tags=["ops-terminal"])


def _require_ttyd() -> None:
    """总开关：未启用时明确 503。"""
    if not get_settings().ops_ttyd_enabled:
        raise HTTPException(
            status_code=503,
            detail="交互终端未启用：请在 .env 设置 OPS_TTYD_ENABLED=true",
        )
    if not get_settings().sandbox_enabled:
        raise HTTPException(
            status_code=503,
            detail="沙箱未启用：请在 .env 设置 SANDBOX_ENABLED=true",
        )


def _need_terminal_approval() -> bool:
    """打开交互终端视为高危：always / on-risky 都要审批。"""
    policy = (get_settings().sandbox_approval or "on-risky").strip().lower()
    return policy in ("always", "on-risky")


class OpenTerminalBody(BaseModel):
    """打开终端请求体。"""

    # 可选：复用已有沙箱；空则新建 vertical=ops
    sessionId: str | None = Field(default=None, max_length=64)
    # P3：只读 ttyd -R
    readonly: bool = False
    # 审批通过后前端置 true
    approved: bool = False


class TerminalPublic(BaseModel):
    """给前端的安全字段：无 port / pid / container_id。"""

    terminalId: str
    sandboxSessionId: str
    terminalUrl: str
    expiresAt: str
    ttlSec: int
    readonly: bool
    status: str
    recording: bool = False


@router.post("/sessions", response_model=TerminalPublic)
async def open_terminal(
    body: OpenTerminalBody,
    user: AuthUser = Depends(require_perm(PERM_OPS_TERMINAL)),
):
    """登录用户打开一个交互终端。"""
    _require_ttyd()

    # 角色门闩（访客等不可开可写终端）
    if not can_open_terminal(user.user_id, readonly=bool(body.readonly)):
        raise HTTPException(
            status_code=403,
            detail="当前角色不能打开可写终端，请改用只读模式",
        )

    sbx = SandboxApplication(user.tenant_id)
    session_id = (body.sessionId or "").strip()

    try:
        if session_id:
            sbx.session_public(session_id)
        else:
            sess = await sbx.acquire(vertical="ops")
            session_id = sess.id
    except AppError as exc:
        # 让全局 AppError handler 记录 internal；DEBUG 时把 docker 原文带回前端
        if get_settings().debug and exc.internal:
            raise HTTPException(
                status_code=exc.http_status,
                detail={
                    "code": exc.code.value,
                    "message": exc.message,
                    "internal": exc.internal,
                },
            ) from exc
        # 非 DEBUG：仍抛 AppError，走统一日志（含 internal），响应只含安全文案
        raise

    # 可写终端才强制审批；只读（ttyd -R）跳过人工确认
    if (
        not body.readonly
        and _need_terminal_approval()
        and not body.approved
    ):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "SANDBOX_APPROVAL_REQUIRED",
                "message": "打开交互终端需要人工审批",
                "risk": "交互式 shell 可在沙箱内执行任意命令",
                "sessionId": session_id,
            },
        )

    mgr = get_ttyd_manager()
    try:
        rec = await mgr.open(
            tenant_id=user.tenant_id,
            user_id=user.user_id,
            sandbox_session_id=session_id,
            readonly=bool(body.readonly),
            approved=bool(body.approved),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return TerminalPublic(**rec.public())


@router.get("/sessions/{terminal_id}", response_model=TerminalPublic)
async def get_terminal(
    terminal_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """查询终端状态。"""
    _require_ttyd()
    mgr = get_ttyd_manager()
    try:
        rec = mgr.get(terminal_id, user_id=user.user_id, tenant_id=user.tenant_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TerminalPublic(**rec.public())


@router.delete("/sessions/{terminal_id}")
async def close_terminal(
    terminal_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """关闭终端：杀 ttyd 进程并回收 ticket。"""
    _require_ttyd()
    await get_ttyd_manager().close(
        terminal_id, user_id=user.user_id, tenant_id=user.tenant_id
    )
    return {"ok": True}


@router.get("/sessions/{terminal_id}/recording")
async def download_recording(
    terminal_id: str,
    user: AuthUser = Depends(get_current_user),
):
    """下载 script 录制的 typescript（优先读宿主机 bind 工作区）。"""
    _require_ttyd()
    mgr = get_ttyd_manager()
    try:
        meta = mgr.recording_meta(
            terminal_id, user_id=user.user_id, tenant_id=user.tenant_id
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    name = str(meta.get("recordingFile") or "")
    session_id = str(meta.get("sandbox_session_id") or "")
    if not name or not session_id:
        raise HTTPException(status_code=404, detail="无录制文件")

    # 防路径穿越：只允许简单文件名
    if "/" in name or "\\" in name or ".." in name or not name.endswith(".log"):
        raise HTTPException(status_code=400, detail="非法录制文件名")

    from shared.path_security import get_project_root

    host = (
        get_project_root()
        / get_settings().sandbox_workspace_host
        / user.tenant_id
        / session_id
        / ".nexora"
        / name
    )
    text = ""
    if host.is_file():
        text = host.read_text(encoding="utf-8", errors="replace")
    else:
        # 会话仍在时，走沙箱 fs_read 兜底
        try:
            sbx = SandboxApplication(user.tenant_id)
            result = await sbx.read_file(
                session_id, f"/workspace/.nexora/{name}"
            )
            text = result.stdout or ""
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(
                status_code=404, detail=f"录制文件不存在：{exc}"
            ) from exc

    from fastapi.responses import PlainTextResponse

    return PlainTextResponse(
        text,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
        },
    )


@router.get("/view")
async def view_terminal(
    ticket: str = Query(..., min_length=16, max_length=128),
):
    """本机调试跳板：302 到 127.0.0.1:{port}{base}/。生产请用 proxy。"""
    _require_ttyd()
    mgr = get_ttyd_manager()
    try:
        rec = mgr.resolve_ticket(ticket)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc

    bind = get_settings().ops_ttyd_bind
    return RedirectResponse(
        url=f"http://{bind}:{rec.port}{rec.proxy_base()}/",
        status_code=302,
    )


# ---------------------------------------------------------------------------
# P2：同源 HTTP / WebSocket 反代
# ---------------------------------------------------------------------------


def _upstream_from_ticket(ticket: str) -> tuple[str, int, str]:
    """ticket → (bind, port, base_path)。失败抛 HTTPException。"""
    try:
        rec = get_ttyd_manager().resolve_ticket(ticket)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return get_settings().ops_ttyd_bind, rec.port, rec.proxy_base()


_HOP_BY_HOP = {
    "transfer-encoding",
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "upgrade",
    "content-encoding",
    "content-length",
    # 禁止嵌入头：否则 iframe 里只会看到浏览器「禁止」页
    "x-frame-options",
    "content-security-policy",
}


@router.api_route("/proxy/{ticket}", methods=["GET", "HEAD", "POST", "OPTIONS"])
@router.api_route(
    "/proxy/{ticket}/{path:path}",
    methods=["GET", "HEAD", "POST", "OPTIONS"],
)
async def proxy_http(ticket: str, request: Request, path: str = "") -> Response:
    """把浏览器 HTTP 请求反代到本机 ttyd（含 base-path）。"""
    _require_ttyd()
    bind, port, base = _upstream_from_ticket(ticket)
    # ttyd 带 -b 时，上游完整路径 = base + / + path
    suffix = path.strip("/")
    if suffix:
        upstream_path = f"{base}/{suffix}"
    else:
        # 目录页：保留尾斜杠，避免 ttyd 再 302
        upstream_path = f"{base}/"
    url = f"http://{bind}:{port}{upstream_path}"
    if request.url.query:
        url = f"{url}?{request.url.query}"

    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in ("host", "content-length")
    }
    body = await request.body()
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            r = await client.request(
                request.method, url, headers=headers, content=body
            )
    except httpx.RequestError as exc:
        _log.warning("ttyd proxy http failed ticket=%s err=%s", ticket[:8], exc)
        raise HTTPException(status_code=502, detail="无法连接 ttyd 上游") from exc

    out_headers = {
        k: v for k, v in r.headers.items() if k.lower() not in _HOP_BY_HOP
    }
    # 显式允许被同源/开发页嵌入（覆盖上游可能残留的 frame 限制）
    out_headers["Content-Security-Policy"] = "frame-ancestors *"
    return Response(content=r.content, status_code=r.status_code, headers=out_headers)


@router.websocket("/proxy/{ticket}/ws")
async def proxy_ws(ws: WebSocket, ticket: str) -> None:
    """双向泵送：浏览器 ↔ 本机 ttyd WebSocket。"""
    if not get_settings().ops_ttyd_enabled:
        await ws.close(code=1013, reason="ttyd disabled")
        return

    try:
        bind, port, base = _upstream_from_ticket(ticket)
    except HTTPException as exc:
        # WebSocket 握手前无法抛 HTTPException 给客户端，只能拒连
        await ws.close(code=1008, reason=str(exc.detail)[:60])
        return

    # 接受客户端；尽量透传子协议（ttyd 常用）
    subprotocols = ws.scope.get("subprotocols") or []
    if subprotocols:
        await ws.accept(subprotocol=subprotocols[0])
    else:
        await ws.accept()

    upstream_url = f"ws://{bind}:{port}{base}/ws"
    try:
        import websockets
    except ImportError:
        await ws.close(code=1011, reason="websockets not installed")
        return

    try:
        async with websockets.connect(
            upstream_url,
            subprotocols=list(subprotocols) if subprotocols else None,
            max_size=8 * 1024 * 1024,
            open_timeout=10,
        ) as up:

            async def client_to_up() -> None:
                try:
                    while True:
                        msg = await ws.receive()
                        if msg["type"] == "websocket.disconnect":
                            break
                        if msg["type"] != "websocket.receive":
                            continue
                        if msg.get("text") is not None:
                            await up.send(msg["text"])
                        elif msg.get("bytes") is not None:
                            await up.send(msg["bytes"])
                except WebSocketDisconnect:
                    pass
                except Exception:
                    _log.debug("ttyd ws client_to_up end", exc_info=True)

            async def up_to_client() -> None:
                try:
                    async for data in up:
                        if isinstance(data, bytes):
                            await ws.send_bytes(data)
                        else:
                            await ws.send_text(str(data))
                except Exception:
                    _log.debug("ttyd ws up_to_client end", exc_info=True)

            await asyncio.gather(client_to_up(), up_to_client())
    except Exception as exc:
        _log.warning("ttyd proxy ws failed ticket=%s err=%s", ticket[:8], exc)
        try:
            await ws.close(code=1011, reason=str(exc)[:60])
        except Exception:
            pass
