"""运维排障 HTTP 门面。

浏览器 → Nexora /api/ops/*（JWT）→ Holmes /api/chat。
不把 Holmes 端口暴露给前端。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from api.auth.deps import AuthUser, get_current_user
from application.ops.holmes_client import HolmesClient, HolmesError
from config.settings import get_settings

router = APIRouter(prefix="/api/ops", tags=["ops"])


def _require_holmes_enabled() -> None:
    """总开关：未启用时明确 503，避免 silent fail。"""
    if not get_settings().holmes_enabled:
        raise HTTPException(
            status_code=503,
            detail="运维引擎未启用：请在 .env 设置 HOLMES_ENABLED=true",
        )


class OpsAskBody(BaseModel):
    """前端提问体。"""

    # 用户自然语言问题
    message: str = Field(default="", max_length=8000)
    # 多轮：把上一轮响应里的 conversation_history 原样带回
    conversation_history: list[dict[str, Any]] | None = None
    # 可选覆盖模型（一般留空，用 HOLMES_DEFAULT_MODEL）
    model: str | None = Field(default=None, max_length=128)
    # P3：用户从沙箱终端侧写的观察（不是 PTY 录像）
    terminalContext: str | None = Field(default=None, max_length=4000)
    # 可选：关联的沙箱会话 id，便于 Holmes / 审计对照
    sandboxSessionId: str | None = Field(default=None, max_length=64)


class OpsAskResponse(BaseModel):
    """统一 camelCase，方便前端。"""

    # Holmes 的主回答（Markdown 文本）
    analysis: str = ""
    # 下一轮要带回的历史
    conversationHistory: list[dict[str, Any]] = Field(default_factory=list)
    # 工具调用摘要（有则展示「调查过程」）
    toolCalls: list[Any] = Field(default_factory=list)
    # Holmes 推荐的后续动作按钮
    followUpActions: list[Any] = Field(default_factory=list)
    # 原始包（调试用，生产可删）
    raw: dict[str, Any] = Field(default_factory=dict)


@router.get("/health")
async def ops_health(user: AuthUser = Depends(get_current_user)):
    """检查门面开关 + Holmes 进程是否可达。"""
    _ = user  # 需要登录，防止未授权扫内网
    _require_holmes_enabled()
    client = HolmesClient()
    ok = client.health()
    return {
        "enabled": True,
        "holmesOk": ok,
        "holmesBase": client.base,
        "model": client.default_model,
    }


@router.post("/ask", response_model=OpsAskResponse)
async def ops_ask(
    body: OpsAskBody,
    user: AuthUser = Depends(get_current_user),
):
    """发起一次运维调查（同步等待 Holmes 跑完工具循环）。"""
    _require_holmes_enabled()
    # P3：把终端观察拼进 ask，避免改 Holmes 协议
    msg = (body.message or "").strip()
    ctx = (body.terminalContext or "").strip()
    if ctx:
        sid = (body.sandboxSessionId or "").strip() or "-"
        msg = (
            f"{msg}\n\n"
            f"---\n"
            f"[Nexora 沙箱终端上下文 sandboxSessionId={sid}]\n"
            f"{ctx}\n"
            f"---"
        )
    client = HolmesClient()
    try:
        data = client.ask(
            message=msg,
            conversation_history=body.conversation_history,
            model=body.model,
            # 把 Nexora 登录名传给 Holmes，便于其侧技能/审计（若支持）
            user_id=user.user_id,
            stream=False,
        )
    except HolmesError as exc:
        code = exc.status_code or 502
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    # Holmes 字段多为 snake_case；这里归一成前端友好的 camelCase
    analysis = data.get("analysis") or data.get("answer") or ""
    if not isinstance(analysis, str):
        analysis = str(analysis)

    history = data.get("conversation_history") or []
    if not isinstance(history, list):
        history = []

    tools = data.get("tool_calls") or data.get("toolCalls") or []
    if not isinstance(tools, list):
        tools = []

    follow = data.get("follow_up_actions") or data.get("followUpActions") or []
    if not isinstance(follow, list):
        follow = []

    return OpsAskResponse(
        analysis=analysis,
        conversationHistory=history,
        toolCalls=tools,
        followUpActions=follow,
        raw=data,
    )