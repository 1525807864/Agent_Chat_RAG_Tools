"""api.routes.chat — 对话 + 真流式（chat 模式）+ 鉴权 + meta(sources/traces)。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse

from api.auth.deps import AuthUser, get_current_user
from api.auth.session_scope import bind_session_id
from api.deps import get_agent_app
from api.schemas import ChatRequest, ChatResponse
from application.services.agent_application import AgentApplication
from domain.run import RequestContext
from observability.tracing import (
    new_request_id,
    set_request_id,
    timed,
    trace,
    trace_error,
)
from shared.errors import AppError

router = APIRouter(prefix="/api", tags=["chat"])


def _scoped_chat_request(req: ChatRequest, user: AuthUser) -> ChatRequest:
    """把客户端 session_id 绑到租户前缀；响应仍回前端原来的短 id。"""
    return req.model_copy(
        update={"session_id": bind_session_id(user.tenant_id, req.session_id)}
    )


def _to_context(req: ChatRequest, *, tenant_id: str) -> RequestContext:
    """HTTP ChatRequest → 领域 RequestContext。"""
    active_file = req.files[0].path if req.files else None
    return RequestContext(
        message=req.message,
        mode=req.mode,
        session_id=req.session_id,
        tenant_id=tenant_id,
        multi_mode=req.multi_mode,
        agent_name=req.agent_name,
        api_key=req.api_key,
        api_base=req.api_base,
        model_name=req.model_name,
        workspace_root=req.workspace_root,
        e2e_base_url=req.e2e_base_url,
        qa_tenant_id=req.qa_tenant_id,
        files=req.files,
        active_file=active_file,
    )


async def _dispatch(
    app: AgentApplication,
    req: ChatRequest,
    *,
    tenant_id: str,
) -> tuple[str, dict]:
    """返回 (answer, extra_meta)。编排统一走 ChatOrchestrator。"""
    ctx = _to_context(req, tenant_id=tenant_id)
    try:
        result = await app.orchestrator.handle(ctx)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return result.answer, dict(result.meta)


def _response_meta(req: ChatRequest, user: AuthUser, extra: dict | None = None) -> dict:
    meta: dict = {
        "user_id": user.user_id,
        "tenant_id": user.tenant_id,
        "request_id": new_request_id(),
    }
    if req.mode == "multi":
        meta["multi_mode"] = req.multi_mode
    mn = (req.model_name or "").strip()
    if mn:
        meta["model_name"] = mn
    if extra:
        meta.update(extra)
    return meta


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> ChatResponse:
    rid = request.headers.get("x-request-id") or new_request_id()
    set_request_id(rid)
    scoped = _scoped_chat_request(req, user)
    with timed(
        "chat",
        mode=req.mode,
        tenant_id=user.tenant_id,
        session_id=req.session_id,
        user_id=user.user_id,
        msg_len=len(req.message or ""),
    ) as bag:
        try:
            answer, extra = await _dispatch(
                app, scoped, tenant_id=user.tenant_id
            )
        except AppError:
            raise
        except Exception as e:
            trace_error(
                "chat_dispatch_error",
                e,
                mode=req.mode,
                tenant_id=user.tenant_id,
            )
            raise HTTPException(status_code=500, detail=str(e)) from e
        bag["answer_len"] = len(answer or "")

    meta = _response_meta(req, user, extra)
    meta["request_id"] = rid
    return ChatResponse(
        session_id=req.session_id,
        mode=req.mode,
        answer=answer,
        meta=meta,
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    request: Request,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
):
    """SSE：编排层 ``orchestrator.stream``；本层只转 SSE 帧。"""
    rid = request.headers.get("x-request-id") or new_request_id()
    set_request_id(rid)
    scoped = _scoped_chat_request(req, user)
    ctx = _to_context(scoped, tenant_id=user.tenant_id)
    trace(
        "chat_stream_accept",
        mode=req.mode,
        tenant_id=user.tenant_id,
        session_id=req.session_id,
        user_id=user.user_id,
        msg_len=len(req.message or ""),
    )

    async def event_generator():
        try:
            start_payload = {
                "session_id": req.session_id,
                "mode": req.mode,
                "tenant_id": user.tenant_id,
                "user_id": user.user_id,
                "request_id": rid,
            }
            yield (
                f"event: start\ndata: "
                f"{json.dumps(start_payload, ensure_ascii=False)}\n\n"
            )

            answer = ""
            usage_meta: dict = {}
            async for ev in app.orchestrator.stream(ctx):
                if ev.kind == "delta" and ev.text:
                    yield (
                        f"event: message\ndata: "
                        f"{json.dumps({'delta': ev.text, 'done': False}, ensure_ascii=False)}\n\n"
                    )
                elif ev.kind == "task":
                    # Intent Guard 意图追踪帧：anchor / check / plan_update / finalize
                    yield (
                        f"event: task\ndata: "
                        f"{json.dumps(ev.meta, ensure_ascii=False)}\n\n"
                    )
                elif ev.kind == "final":
                    answer = ev.answer
                    usage_meta = dict(ev.meta or {})

            done = {
                "delta": "",
                "done": True,
                "answer": answer,
                "usage": usage_meta.get("usage"),
                "tenant_usage": usage_meta.get("tenant_usage"),
                "task_plan": usage_meta.get("task_plan"),
            }
            trace(
                "chat_stream_done",
                mode=req.mode,
                answer_len=len(answer or ""),
            )
            yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"
        except Exception as e:
            trace_error(
                "chat_stream_error",
                e,
                mode=req.mode,
                tenant_id=user.tenant_id,
            )
            err = {"detail": str(e)}
            yield f"event: error\ndata: {json.dumps(err, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": rid,
        },
    )
