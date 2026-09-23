"""统一编排入口：Provider 路由（Cursor）→ Capability 路由（mode）。"""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncIterator

from application.routing.handoff import try_cursor_answer
from billing.usage import LEDGER
from domain.run import RequestContext, RunResult, StreamEvent
from observability.tracing import trace
from orchestration.capabilities import Capability, default_capabilities

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class ChatOrchestrator:
    """一次聊天请求的主干流水线。

    1. Security 已在各 UseCase / ask_* 内做；此处不重复
    2. ProviderRouter：改代码类请求可走 Cursor
    3. CapabilityRouter：按 mode 分发到对应 UseCase
    4. 计费 / 落库（Cursor 分支）
    5. ``stream``：SSE 用，API 只消费 StreamEvent
    """

    def __init__(
        self,
        app: AgentApplication,
        *,
        capabilities: dict[str, Capability] | None = None,
    ) -> None:
        self._app = app
        self._caps = capabilities or default_capabilities()

    async def handle(self, ctx: RequestContext) -> RunResult:
        """返回统一 RunResult；未知 mode 抛 ValueError（由 API 转 400）。"""
        cursor = await self._try_cursor(ctx)
        if cursor is not None:
            return cursor
        return await self._run_capability(ctx)

    async def stream(self, ctx: RequestContext) -> AsyncIterator[StreamEvent]:
        """流式编排：yield delta，最后一条 kind=final 带完整 answer。

        - Cursor 命中 / 非 chat mode：整段一次 delta
        - chat：走 ChatUseCase.astream（Skills + Memory，与 execute 同源）
        """
        cursor = await self._try_cursor(ctx)
        if cursor is not None:
            yield StreamEvent(kind="delta", text=cursor.answer)
            yield StreamEvent(kind="final", answer=cursor.answer)
            return

        if ctx.mode == "chat":
            async for ev in self._app.use_cases.chat.astream(
                ctx.message,
                session_id=ctx.session_id,
                api_key=ctx.api_key,
                api_base=ctx.api_base,
                model_name=ctx.model_name,
                active_file=ctx.active_file,
                files=ctx.files,
            ):
                yield ev
            LEDGER.add(ctx.tenant_id, requests=1)
            return

        result = await self._run_capability(ctx)
        yield StreamEvent(kind="delta", text=result.answer)
        yield StreamEvent(kind="final", answer=result.answer)

    async def _try_cursor(self, ctx: RequestContext) -> RunResult | None:
        cursor = await try_cursor_answer(
            mode=ctx.mode,
            message=ctx.message,
            session_id=ctx.session_id,
            tenant_id=ctx.tenant_id,
            api_key=self._app.settings.cursor_api_key,
            model=self._app.settings.cursor_model,
            workspace_root=ctx.workspace_root,
        )
        if cursor is None:
            return None
        answer, cursor_meta = cursor
        await self._app.use_cases.session.persist_turn(
            ctx.session_id, ctx.message, answer
        )
        LEDGER.add(ctx.tenant_id, requests=1)
        trace("orchestrator_cursor", reason=cursor_meta.get("route_reason"))
        return RunResult(
            answer=answer,
            meta={"capability": "cursor", **cursor_meta},
        )

    async def _run_capability(self, ctx: RequestContext) -> RunResult:
        cap = self._caps.get(ctx.mode)
        if cap is None:
            raise ValueError(f"未知 mode: {ctx.mode}")

        if ctx.mode != "agent" and ctx.files:
            from dataclasses import replace

            from application.prompts.files import build_files_prefix

            prefixed = (
                build_files_prefix(ctx.files) + "用户请求：\n" + ctx.message
            )
            ctx = replace(ctx, message=prefixed)

        result = await cap.run(self._app, ctx)
        if ctx.mode in {"chat", "agent"}:
            LEDGER.add(ctx.tenant_id, requests=1)
        trace("orchestrator_capability", mode=ctx.mode)
        return result
