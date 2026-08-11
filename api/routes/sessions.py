"""api.routes.sessions — 会话历史相关 HTTP 路由

本模块职责
==========
对 ``memory.session_store``（经 ``AgentApplication`` 薄封装）做 CRUD 风格暴露：
- 列出所有有历史的 session_id
- 查询某一会话的近期消息
- 删除（清空）某一会话

不负责
======
创建会话：会话是「写消息时自然产生」的，无需单独 POST 创建；
前端生成 UUID 作为 ``session_id`` 即可在首次 chat 时落库。

存储后端
========
具体是 Redis 还是 SQLite，由 ``Settings.memory_backend`` / ``.env`` 决定；
本路由不感知实现细节，只调用 ``AgentApplication`` 上的会话方法。
"""

from fastapi import APIRouter, Depends, HTTPException

from api.deps import get_agent_app
from api.schemas import (
    SessionHistoryResponse,
    SessionListResponse,
    SessionMessage,
)
from application.services.agent_application import AgentApplication

router = APIRouter(prefix="/api/sessions", tags=["sessions"])


@router.get("", response_model=SessionListResponse)
async def list_sessions(
    app: AgentApplication = Depends(get_agent_app),
) -> SessionListResponse:
    """列出当前存储后端中出现过的所有会话 ID。

    调用时机
    --------
    前端侧边栏「历史会话」列表刷新时。

    边界
    ----
    - 空库：返回 ``sessions: []``，不是 404。
    - Redis SCAN / SQLite DISTINCT 的结果顺序不保证按「最近活跃」排序；
      若产品需要排序，应在业务层扩展元数据后再改本接口。
    """
    try:
        sessions = await app.list_sessions()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return SessionListResponse(sessions=sessions)


@router.get("/{session_id}", response_model=SessionHistoryResponse)
async def get_session_history(
    session_id: str,
    app: AgentApplication = Depends(get_agent_app),
) -> SessionHistoryResponse:
    """获取指定会话的近期消息（默认最多 20 条，与业务层 get_chat_history 一致）。

    路径参数
    --------
    session_id:
        与 ``ChatRequest.session_id`` 同一套命名空间。

    边界
    ----
    - 会话不存在或尚无消息：返回空 ``messages`` 列表，HTTP 200。
      （不使用 404，避免前端把「新会话」误判为错误。）
    - 仅返回 role/content；时间戳等内部字段不对外暴露。
    """
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
    app: AgentApplication = Depends(get_agent_app),
) -> dict:
    """清空并删除指定会话下的全部消息。

    语义
    ----
    对应 ``BaseSessionStore.clear_session``：删除该 session_id 的历史记录。
    幂等：对不存在的 session_id 重复删除也应成功（底层 DELETE 影响 0 行即可）。

    返回值
    ------
    简单 JSON ``{"ok": true, "session_id": "..."}``，便于前端确认操作对象。
    """
    try:
        await app.delete_session(session_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    return {"ok": True, "session_id": session_id}
