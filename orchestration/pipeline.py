"""统一编排入口：Provider 路由（Cursor）→ Capability 路由（mode）。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, AsyncIterator

from application.routing.handoff import try_cursor_answer
from domain.run import RequestContext, RunResult, StreamEvent
from observability.langsmith_trace import langsmith_turn
from observability.tracing import timed, trace, trace_error, trace_warn
from orchestration.capabilities import Capability, default_capabilities
from utils.logger import get_logger

_log = get_logger("nexora.orchestrator")

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class ChatOrchestrator:
    """一次聊天请求的主干流水线。"""

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
        with langsmith_turn(ctx, name="chat.handle"):
            with timed(
                "orchestrator_handle",
                mode=ctx.mode,
                tenant_id=ctx.tenant_id,
                session_id=ctx.session_id,
            ) as bag:
                result = await self._handle_body(ctx)
                bag["answer_len"] = len(result.answer or "")
                bag["capability"] = (result.meta or {}).get("capability")
                return result

    async def _handle_body(self, ctx: RequestContext) -> RunResult:
        cursor = await self._try_cursor(ctx)
        if cursor is not None:
            return cursor
        return await self._run_capability(ctx)

    async def stream(self, ctx: RequestContext) -> AsyncIterator[StreamEvent]:
        """流式编排：yield delta，最后一条 kind=final（可带 usage meta）。"""
        with langsmith_turn(ctx, name="chat.stream"):
            async for ev in self._stream_body(ctx):
                yield ev

    async def _stream_body(self, ctx: RequestContext) -> AsyncIterator[StreamEvent]:
        cursor = await self._try_cursor(ctx)
        if cursor is not None:
            yield StreamEvent(kind="delta", text=cursor.answer)
            yield StreamEvent(
                kind="final",
                answer=cursor.answer,
                meta=dict(cursor.meta or {}),
            )
            return

        if ctx.mode == "chat":
            async for ev in self._app.use_cases.chat.astream(
                ctx.message,
                session_id=ctx.session_id,
                tenant_id=ctx.tenant_id,
                api_key=ctx.api_key,
                api_base=ctx.api_base,
                model_name=ctx.model_name,
                active_file=ctx.active_file,
                files=ctx.files,
            ):
                yield ev
            return

        # 其它 mode：后台跑能力，期间把 Intent Guard 的 task 帧实时推给前端
        # （这些模式本非真流式，答案为整段；task 帧只是「执行过程可见」）
        from dataclasses import replace

        queue: asyncio.Queue = asyncio.Queue()
        ctx = replace(ctx, task_events=queue)
        run_task = asyncio.create_task(self._run_capability(ctx))
        while True:
            drained = False
            while True:
                try:
                    payload = queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                drained = True
                yield StreamEvent(kind="task", meta=payload)
            if run_task.done():
                break
            if not drained:
                await asyncio.sleep(0.05)

        # 排空剩余帧（能力结束前最后一瞬间写入的）
        while True:
            try:
                payload = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            yield StreamEvent(kind="task", meta=payload)

        result = await run_task  # 异常在此抛出，由 API 转 error 帧
        yield StreamEvent(kind="delta", text=result.answer)
        yield StreamEvent(
            kind="final",
            answer=result.answer,
            meta=dict(result.meta or {}),
        )

    async def _try_cursor(self, ctx: RequestContext) -> RunResult | None:
        try:
            cursor = await try_cursor_answer(
                mode=ctx.mode,
                message=ctx.message,
                session_id=ctx.session_id,
                tenant_id=ctx.tenant_id,
                api_key=self._app.settings.cursor_api_key,
                model=self._app.settings.cursor_model,
                workspace_root=ctx.workspace_root,
            )
        except Exception as exc:  # noqa: BLE001
            trace_warn(
                "orchestrator_cursor_error",
                error_type=type(exc).__name__,
                error=str(exc)[:200],
            )
            return None
        if cursor is None:
            return None
        answer, cursor_meta = cursor
        await self._app.use_cases.session.persist_turn(
            ctx.session_id, ctx.message, answer
        )
        # Cursor 无官方 token 时只记请求次数
        try:
            from domain.usage import TurnUsage
            from billing.recorder import record_turn

            usage_meta = record_turn(
                self._app.usage_ledger,
                ctx.tenant_id,
                TurnUsage(requests=1, model="cursor"),
            )
        except Exception:  # noqa: BLE001
            usage_meta = {}
            _log.warning("Cursor 用量记账失败", exc_info=True)
        trace("orchestrator_cursor", reason=cursor_meta.get("route_reason"))
        return RunResult(
            answer=answer,
            meta={"capability": "cursor", **cursor_meta, **usage_meta},
        )

    async def _run_capability(self, ctx: RequestContext) -> RunResult:
        cap = self._caps.get(ctx.mode)
        if cap is None:
            trace_error("orchestrator_unknown_mode", mode=ctx.mode)
            raise ValueError(f"未知 mode: {ctx.mode}")

        if ctx.mode != "agent" and ctx.files:
            from dataclasses import replace

            from application.prompts.files import build_files_prefix

            prefixed = (
                build_files_prefix(ctx.files) + "用户请求：\n" + ctx.message
            )
            ctx = replace(ctx, message=prefixed)
            trace("orchestrator_files_prefixed", files=len(ctx.files or []))

        try:
            result = await cap.run(self._app, ctx)
        except Exception as exc:
            trace_error(
                "orchestrator_capability_failed",
                exc,
                mode=ctx.mode,
                tenant_id=ctx.tenant_id,
            )
            raise
        # chat 已在 UseCase 记账；其它 mode 暂记请求次数（后续可补 token）
        if ctx.mode != "chat" and "usage" not in (result.meta or {}):
            try:
                from domain.usage import TurnUsage
                from billing.recorder import record_turn

                extra = record_turn(
                    self._app.usage_ledger,
                    ctx.tenant_id,
                    TurnUsage(requests=1),
                )
                result = result.with_meta(**extra)
            except Exception:  # noqa: BLE001
                _log.warning("Capability 用量记账失败 mode=%s", ctx.mode, exc_info=True)
        trace(
            "orchestrator_capability",
            mode=ctx.mode,
            answer_len=len(result.answer or ""),
        )
        return result
