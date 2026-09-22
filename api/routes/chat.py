"""api.routes.chat — 对话 + 真流式（chat 模式）+ 鉴权 + meta(sources/traces)。"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage

from api.auth.deps import AuthUser, get_current_user
from api.auth.session_scope import bind_session_id
from api.deps import get_agent_app
from api.schemas import ChatRequest, ChatResponse
from application.routing.handoff import try_cursor_answer
from application.services.agent_application import AgentApplication
from billing.usage import LEDGER
from observability.tracing import new_request_id, set_request_id, trace
from shared.errors import AppError

router = APIRouter(prefix="/api", tags=["chat"])


def _scoped_chat_request(req: ChatRequest, user: AuthUser) -> ChatRequest:
    """把客户端 session_id 绑到租户前缀；响应仍回前端原来的短 id。"""
    return req.model_copy(
        update={"session_id": bind_session_id(user.tenant_id, req.session_id)}
    )


async def _persist_turn(app: AgentApplication, session_id: str, user_input: str, answer: str) -> None:
    """Cursor 分支不经过 ask_chat，这里单独落库，会话列表才能用最后一句当标题。"""
    try:
        if app.memory is None:
            await app.init_session_store()
        if app.memory is not None:
            await app.memory.persist_turn(
                session_id=session_id,
                user_input=user_input,
                assistant_output=answer,
            )
        elif app.session_store:
            await app.session_store.add_message(session_id, "user", user_input)
            await app.session_store.add_message(session_id, "assistant", answer)
    except Exception as exc:  # noqa: BLE001
        trace("cursor_persist_fail", error=str(exc))


async def _dispatch(
    app: AgentApplication,
    req: ChatRequest,
    *,
    tenant_id: str,
) -> tuple[str, dict]:
    """返回 (answer, extra_meta)。"""
    llm_kwargs = {
        "api_key": req.api_key,
        "api_base": req.api_base,
        "model_name": req.model_name,
    }
    active_file = req.files[0].path if req.files else None
    message = req.message
    if req.mode != "agent" and req.files:
        message = (
            AgentApplication._build_files_prefix(req.files)
            + "用户请求：\n"
            + req.message
        )

    extra: dict = {}
    # 先问分配器。None 表示这条仍走下面的 DeepSeek 分支。
    settings = app.settings
    cursor_hit = await try_cursor_answer(
        mode=req.mode,
        message=req.message,
        session_id=req.session_id,
        tenant_id=tenant_id,
        api_key=settings.cursor_api_key,
        model=settings.cursor_model,
        workspace_root=req.workspace_root,
    )
    if cursor_hit is not None:
        answer, cursor_meta = cursor_hit
        extra.update(cursor_meta)
        await _persist_turn(app, req.session_id, req.message, answer)
        LEDGER.add(tenant_id, requests=1)
        return answer, extra

    if req.mode == "chat":
        answer = await app.ask_chat(
            req.message,
            session_id=req.session_id,
            active_file=active_file,
            files=req.files,
            **llm_kwargs,
        )
        LEDGER.add(tenant_id, requests=1)
        return answer, extra

    if req.mode == "rag":
        answer, sources = await app.ask_rag(
            message, tenant_id=tenant_id, **llm_kwargs
        )
        extra["sources"] = sources
        return answer, extra

    if req.mode == "consult":
        answer, sources = await app.ask_consult(
            message,
            tenant_id=tenant_id,
            session_id=req.session_id,
            **llm_kwargs,
        )
        extra["sources"] = sources
        return answer, extra

    if req.mode == "graph-rag":
        answer, sources = await app.ask_graph_rag(
            message, tenant_id=tenant_id, **llm_kwargs
        )
        extra["sources"] = sources
        return answer, extra

    if req.mode == "agent":
        answer = await app.ask_agent(
            req.message,
            agent_name=req.agent_name,
            workspace_root=req.workspace_root,
            files=req.files,
            active_file=active_file,
            e2e_base_url=req.e2e_base_url,
            qa_tenant_id=req.qa_tenant_id,
            **llm_kwargs,
        )
        LEDGER.add(tenant_id, requests=1)
        return answer, extra

    if req.mode == "multi":
        result = await app.ask_multi_agent(
            message, mode=req.multi_mode, **llm_kwargs
        )
        extra["execution_log"] = result.get("execution_log", [])
        extra["agent_outputs"] = result.get("agent_outputs", {})
        extra["total_time_ms"] = result.get("total_time_ms")
        extra["success"] = result.get("success")
        return str(result.get("final_answer") or ""), extra

    raise HTTPException(status_code=400, detail=f"未知 mode: {req.mode}")


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
    trace("chat", mode=req.mode, tenant_id=user.tenant_id)
    scoped = _scoped_chat_request(req, user)
    try:
        answer, extra = await _dispatch(app, scoped, tenant_id=user.tenant_id)
    except AppError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

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
    """SSE：chat 模式真流式；其它模式仍整段推一次。"""
    rid = request.headers.get("x-request-id") or new_request_id()
    set_request_id(rid)
    scoped = _scoped_chat_request(req, user)

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

            # 流式 chat 不经过 _dispatch，这里要单独问一次分配器。
            cursor_hit = await try_cursor_answer(
                mode=req.mode,
                message=req.message,
                session_id=scoped.session_id,
                tenant_id=user.tenant_id,
                api_key=app.settings.cursor_api_key,
                model=app.settings.cursor_model,
                workspace_root=req.workspace_root,
            )
            if cursor_hit is not None:
                answer, _meta = cursor_hit
                await _persist_turn(app, scoped.session_id, req.message, answer)
                LEDGER.add(user.tenant_id, requests=1)
                yield (
                    f"event: message\ndata: "
                    f"{json.dumps({'delta': answer, 'done': False}, ensure_ascii=False)}\n\n"
                )
            # chat 模式：直接 astream LLM（无 skills/memory 简化版真流式）
            elif req.mode == "chat":
                llm = app._resolve_llm(
                    api_key=req.api_key,
                    api_base=req.api_base,
                    model_name=req.model_name,
                )
                messages = [
                    SystemMessage(content="你是一个优秀的AI助手, 请简洁准确地回答用户问题。"),
                    HumanMessage(content=req.message),
                ]
                full = []
                async for chunk in llm.astream(messages):
                    text = ""
                    content = getattr(chunk, "content", None)
                    if isinstance(content, str):
                        text = content
                    elif content is not None:
                        text = str(content)
                    if not text:
                        continue
                    full.append(text)
                    yield (
                        f"event: message\ndata: "
                        f"{json.dumps({'delta': text, 'done': False}, ensure_ascii=False)}\n\n"
                    )
                answer = "".join(full)
                LEDGER.add(user.tenant_id, requests=1)
                # 异步落库（不阻塞 SSE）
                try:
                    if app.memory is None:
                        await app.init_session_store()
                    if app.memory is not None:
                        await app.memory.persist_turn(
                            session_id=scoped.session_id,
                            user_input=req.message,
                            assistant_output=answer,
                        )
                    elif app.session_store:
                        await app.session_store.add_message(
                            scoped.session_id, "user", req.message
                        )
                        await app.session_store.add_message(
                            scoped.session_id, "assistant", answer
                        )
                except Exception as exc:  # noqa: BLE001
                    # 流式已完成，落库失败只记日志
                    trace("stream_persist_fail", error=str(exc))
            else:
                answer, _extra = await _dispatch(
                    app, scoped, tenant_id=user.tenant_id
                )
                yield (
                    f"event: message\ndata: "
                    f"{json.dumps({'delta': answer, 'done': False}, ensure_ascii=False)}\n\n"
                )

            done = {"delta": "", "done": True, "answer": answer}
            yield f"event: done\ndata: {json.dumps(done, ensure_ascii=False)}\n\n"
        except Exception as e:
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
