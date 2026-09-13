"""api.routes.sessions — 会话历史相关 HTTP 路由

鉴权：列表 / 查询 / 删除 / memory 均依赖 ``get_current_user``。
（后续可按 tenant 过滤 session 列表；当前仅要求登录。）
"""

from fastapi import APIRouter, Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
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
    """列出当前存储后端中出现过的所有会话 ID。需鉴权。"""
    _ = user
    try:
        sessions = await app.list_sessions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return SessionListResponse(sessions=sessions)


@router.get("/{session_id}/memory", response_model=SessionMemoryResponse)
async def get_session_memory(
    session_id: str,
    user: AuthUser = Depends(get_current_user),
    app: AgentApplication = Depends(get_agent_app),
) -> SessionMemoryResponse:
    """读取会话记忆快照。需鉴权。"""
    _ = user
    try:
        if app.memory is None and app.session_store is None:
            await app.init_session_store()
        snap = app.get_session_memory_snapshot(session_id)
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
    """获取指定会话的近期消息。需鉴权。"""
    _ = user
    try:
        raw = await app.get_chat_history(session_id)
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
    """清空并删除指定会话。需鉴权。"""
    try:
        await app.delete_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "ok": True,
        "session_id": session_id,
        "tenant_id": user.tenant_id,
        "user_id": user.user_id,
    }
