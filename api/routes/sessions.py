"""会话历史 HTTP 路由：必须登录，且只能看见本租户的 session。"""

from fastapi import APIRouter, Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
from api.auth.session_scope import bind_session_id, public_session_id
from api.deps import get_agent_app
from api.schemas import (
    SessionHistoryResponse,
    SessionListResponse,
    SessionMemoryResponse,
    SessionMessage,
    SolipNextQuestion,
)
from application.services.agent_application import AgentApplication

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> SessionListResponse:
    try:
        sessions = await app.list_sessions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    visible = [
        sid
        for stored in sessions
        if (sid := public_session_id(user.tenant_id, stored)) is not None
    ]
    return SessionListResponse(sessions=visible)


@router.get("/{session_id}/memory", response_model=SessionMemoryResponse)
async def get_session_memory(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> SessionMemoryResponse:
    scoped = bind_session_id(user.tenant_id, session_id)
    try:
        if app.memory is None and app.session_store is None:
            await app.init_session_store()
        snap = app.get_session_memory_snapshot(scoped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    next_qs: list[SolipNextQuestion] = []
    for q in snap.get("next_questions") or []:
        if isinstance(q, dict) and q.get("question"):
            next_qs.append(
                SolipNextQuestion(
                    question=str(q.get("question", "")),
                    confidence=float(q.get("confidence", 0.5) or 0.5),
                    reason=str(q.get("reason", "") or ""),
                )
            )
        elif isinstance(q, str) and q.strip():
            next_qs.append(SolipNextQuestion(question=q.strip()))

    return SessionMemoryResponse(
        session_id=session_id,
        intent_hypothesis=str(snap.get("intent_hypothesis") or ""),
        open_loops=[str(x) for x in (snap.get("open_loops") or [])],
        next_questions=next_qs,
        summary=str(snap.get("summary") or ""),
    )


@router.get("/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> SessionHistoryResponse:
    scoped = bind_session_id(user.tenant_id, session_id)
    try:
        raw = await app.get_chat_history(scoped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    messages = [
        SessionMessage(role=m.get("role", ""), content=m.get("content", ""))
        for m in raw
    ]
    return SessionHistoryResponse(session_id=session_id, messages=messages)


@router.delete("/{session_id}")
async def delete_session(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> dict:
    scoped = bind_session_id(user.tenant_id, session_id)
    try:
        await app.delete_session(scoped)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "ok": True,
        "session_id": session_id,
        "tenant_id": user.tenant_id,
        "user_id": user.user_id,
    }
