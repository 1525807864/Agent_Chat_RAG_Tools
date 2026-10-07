"""会话历史 HTTP 路由：必须登录，且只能看见本租户的 session。"""

from fastapi import APIRouter, Depends, HTTPException

from api.auth.deps import AuthUser, get_current_user
from api.auth.session_scope import bind_session_id, public_session_id
from api.deps import get_agent_app
from api.schemas import (
    IntentTaskDTO,
    SessionHistoryResponse,
    SessionListResponse,
    SessionMemoryResponse,
    SessionMessage,
    SolipNextQuestion,
    TaskPlanDTO,
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

    tp = snap.get("task_plan") or {}
    plan_tasks: list[IntentTaskDTO] = []
    for t in tp.get("tasks") or []:
        if isinstance(t, dict) and t.get("title"):
            plan_tasks.append(
                IntentTaskDTO(
                    id=str(t.get("id") or ""),
                    title=str(t.get("title") or ""),
                    status=str(t.get("status") or "pending"),
                    closed_by=str(t.get("closed_by") or ""),
                    closed_at=str(t.get("closed_at") or ""),
                    sort=int(t.get("sort") or 0),
                )
            )
    task_plan = TaskPlanDTO(
        goal=str(tp.get("goal") or ""),
        goal_raw=str(tp.get("goal_raw") or ""),
        turn_created=int(tp.get("turn_created") or 1),
        last_confirmed_turn=int(tp.get("last_confirmed_turn") or 0),
        anchor_history=list(tp.get("anchor_history") or []),
        tasks=plan_tasks,
        version=int(tp.get("version") or 0),
        check_errors=int(tp.get("check_errors") or 0),
        drift_count=int(tp.get("drift_count") or 0),
        blocked_actions=int(tp.get("blocked_actions") or 0),
    )

    return SessionMemoryResponse(
        session_id=session_id,
        intent_hypothesis=str(snap.get("intent_hypothesis") or ""),
        open_loops=[str(x) for x in (snap.get("open_loops") or [])],
        next_questions=next_qs,
        summary=str(snap.get("summary") or ""),
        task_plan=task_plan,
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
    """删除一条会话。

    库里可能有两种 id：
    - 新数据：``default::web-xxx``（chat 路由写入前 bind 过）
    - 旧数据：``web-xxx`` / ``explain-xxx``（没有租户前缀）

    列表对 default 租户会把无前缀 id 原样返回。
    若只删 bind 后的 id，旧行删不到，接口仍返回 200，列表看起来没变化。
    """
    scoped = bind_session_id(user.tenant_id, session_id)
    # 先删带租户前缀的行
    targets = [scoped]
    # 无前缀、且属于当前租户（default 的旧数据）时，再删原始 id
    raw = session_id.strip()
    if raw and raw != scoped and public_session_id(user.tenant_id, raw) == raw:
        targets.append(raw)
    try:
        for sid in targets:
            await app.delete_session(sid)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {
        "ok": True,
        "session_id": session_id,
        "tenant_id": user.tenant_id,
        "user_id": user.user_id,
    }
