"""api.routes.chat — 对话相关 HTTP 路由

本模块职责
==========
提供两类接口：
1. ``POST /api/chat``          — 同步（非流式）整段返回答案
2. ``POST /api/chat/stream``   — SSE 占位流式（当前仍是整段生成后再推事件）

与业务核心的关系
================
真正的推理、RAG、Agent 编排都在 ``application.AgentApplication``：
本模块的 ``_dispatch`` 仅按 ``ChatRequest.mode`` 做「路由器」映射，
不复制业务逻辑，以便 CLI（``main.py``）与 HTTP 行为一致。

SSE 为何是「占位」
==================
``llm_deepseek.DeepSeekChatModel`` 目前只实现 ``_generate``，没有真正的
token 级 ``_astream``。前端仍可先按 SSE 协议对接（start → message → done），
待 LLM 层支持流式后再改 ``event_generator`` 内的推送粒度即可。
"""

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from api.deps import get_agent_app
from api.schemas import ChatRequest, ChatResponse
from application.services.agent_application import AgentApplication
from shared.errors import AppError

# prefix="/api"：与 sessions/knowledge 保持同一 API 命名空间；
# tags=["chat"]：OpenAPI 文档中单独分组，便于前端对照。
router = APIRouter(prefix="/api", tags=["chat"])


async def _dispatch(app: AgentApplication, req: ChatRequest) -> str:
    """按 mode 分发到 AgentApplication 对应方法，并返回答案字符串。

    参数
    ----
    app:
        已初始化的业务单例（含 session_store、向量库等）。
    req:
        已通过 Pydantic 校验的请求体。

    返回值
    ------
    助手最终文本。业务层失败时部分 ask_* 会返回「对话出错: ...」字符串而非抛异常；
    若抛出未知异常，由上层路由捕获并转为 HTTP 500。

    边界
    ----
    - 未知 mode：理论上 Pydantic Literal 已拦截；此处再防一层并返回 400。
    - ``multi_mode`` / ``agent_name`` 仅在对应 mode 下使用，其它模式忽略字段。
    - api_key / api_base / model_name 原样传给 ask_*（空则业务层回退 .env）。
    """
    # 本轮模型凭证：请求级优先，后端 _resolve_llm 负责回退到 Settings/.env
    llm_kwargs = {
        "api_key": req.api_key,
        "api_base": req.api_base,
        "model_name": req.model_name,
    }

    # 非 agent 模式：若带了打开文件，把内容拼进 message 前缀（只读上下文）
    message = req.message
    if req.mode != "agent" and req.files:
        message = AgentApplication._build_files_prefix(req.files) + "用户请求：\n" + req.message

    if req.mode == "chat":
        # chat 模式才会按 session_id 读写历史；其它模式不带会话上下文。
        return await app.ask_chat(message, session_id=req.session_id, **llm_kwargs)
    if req.mode == "rag":
        return await app.ask_rag(message, **llm_kwargs)
    if req.mode == "graph-rag":
        return await app.ask_graph_rag(message, **llm_kwargs)
    if req.mode == "agent":
        return await app.ask_agent(
            req.message,
            agent_name=req.agent_name,
            workspace_root=req.workspace_root,
            files=req.files,
            **llm_kwargs,
        )
    if req.mode == "multi":
        # multi_mode: sequential | debate | router → MultiAgentOrchestrator
        return await app.ask_multi_agent(message, mode=req.multi_mode, **llm_kwargs)
    raise HTTPException(status_code=400, detail=f"未知 mode: {req.mode}")


def _response_meta(req: ChatRequest) -> dict:
    """组装响应 meta：可带回 model_name / multi_mode，绝不带回 api_key。"""
    meta: dict = {}
    if req.mode == "multi":
        meta["multi_mode"] = req.multi_mode
    # 仅回传「本轮请求里写明的模型名」，方便前端确认；不猜服务端默认值
    mn = (req.model_name or "").strip()
    if mn:
        meta["model_name"] = mn
    return meta


@router.post("/chat", response_model=ChatResponse)
async def chat(
    req: ChatRequest,
    app: AgentApplication = Depends(get_agent_app),
) -> ChatResponse:
    """非流式对话：一次请求，等待完整答案后返回 JSON。

    调用时机
    --------
    前端不需要打字机效果、或调试接口时优先用本端点；实现简单、易测。

    错误处理
    --------
    业务异常统一包装为 HTTP 500，``detail`` 为异常字符串。
    安全拦截（内容过滤）通常以答案文本 ``[安全拦截] ...`` 返回，不视为 HTTP 错误。
    """
    try:
        answer = await _dispatch(app, req)
    except AppError:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e

    return ChatResponse(
        session_id=req.session_id,
        mode=req.mode,
        answer=answer,
        # multi_mode / model_name 可回传；api_key 永不进 meta
        meta=_response_meta(req),
    )


@router.post("/chat/stream")
async def chat_stream(
    req: ChatRequest,
    app: AgentApplication = Depends(get_agent_app),
):
    """SSE 占位流式接口。

    协议约定（event 名）
    --------------------
    - ``start``  ：携带 session_id/mode，前端可显示「生成中」
    - ``message``：携带 ``delta``（当前为完整答案一次性放入）与 ``done: false``
    - ``done``   ：结束标记，并再次附带完整 ``answer`` 便于前端落库
    - ``error``  ：生成过程异常时推送，``detail`` 为错误信息

    实现说明
    --------
    当前 DeepSeekChatModel 尚无真正 token 流式，先整段返回一次 event，
    前端可先按 SSE 协议对接；以后再改 ``llm_deepseek`` 的流式生成与本生成器。

    响应头
    ------
    - ``Cache-Control: no-cache``：禁止中间层缓存流
    - ``X-Accel-Buffering: no``：提醒 Nginx 不要缓冲 SSE（若前面有反代）
    """

    async def event_generator():
        """异步生成器：按 SSE 文本格式 yield 字符串块。

        SSE 格式要点：``event: <name>\\ndata: <json>\\n\\n``。
        ``ensure_ascii=False`` 保证中文不以 \\uXXXX 转义，前端直接可读。
        """
        try:
            # 先发 start，方便前端立刻进入 loading，而不必等 LLM 返回。
            yield (
                f"event: start\ndata: "
                f"{json.dumps({'session_id': req.session_id, 'mode': req.mode}, ensure_ascii=False)}"
                f"\n\n"
            )

            answer = await _dispatch(app, req)

            # 兼容前端增量渲染：将来可把 answer 按句/按 token 切开多次 yield；
            # 现在一次推完，行为上等价于「只有一个大 delta」。
            payload = {"delta": answer, "done": False}
            yield f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

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
        },
    )
