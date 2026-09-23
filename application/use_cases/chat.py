"""普通对话用例：Memory + Skills + LLM（同步 + 真流式同源）。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, AsyncIterator, Optional

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from domain.run import RunResult, StreamEvent
from shared.errors import AppError, sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication

_SYSTEM = (
    "你是一个优秀的AI助手, 请简洁准确地回答用户问题。\n"
    "若系统提供了【相关记忆 / Solip 假设】，可作参考，"
    "但不要当成用户已确认的事实强行使用。\n"
    "若系统提供了 # Active Skill，请优先遵循该技能说明。\n"
    "{summary_block}"
)


@dataclass
class _PreparedTurn:
    """本轮对话已解析完 Skills / Memory 后的可执行上下文。"""

    llm: object
    llm_input: str
    history: list
    system_extra: str
    memory_session_id: str
    persist_user: str


class ChatUseCase:
    """负责带会话记忆的普通对话（不含 RAG / Agent 工具环）。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str,
        *,
        session_id: str = "default",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        active_file: Optional[str] = None,
        files: list | None = None,
    ) -> RunResult:
        answer = await self._run(
            message,
            session_id=session_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            active_file=active_file,
            files=files,
        )
        return RunResult(answer=answer, meta={"capability": "chat"})

    async def astream(
        self,
        message: str,
        *,
        session_id: str = "default",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        active_file: Optional[str] = None,
        files: list | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """真流式：与 execute 同路径（Skills + Memory），yield delta，末条 final。"""
        app = self._app
        blocked = await app.security.guard(message, rate_limit=True)
        if blocked:
            yield StreamEvent(kind="delta", text=blocked)
            yield StreamEvent(kind="final", answer=blocked)
            return

        try:
            prep = await self._prepare(
                message,
                session_id=session_id,
                api_key=api_key,
                api_base=api_base,
                model_name=model_name,
                active_file=active_file,
                files=files,
            )
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            err = f"对话出错: {sanitize_exception_message(e)}"
            app.logger.error("对话准备失败: %s", e)
            yield StreamEvent(kind="delta", text=err)
            yield StreamEvent(kind="final", answer=err)
            return

        prompt = self._prompt()
        chain = prompt | prep.llm | StrOutputParser()
        parts: list[str] = []
        try:
            async for chunk in chain.astream(
                {
                    "input": prep.llm_input,
                    "history": prep.history,
                    "summary_block": prep.system_extra,
                }
            ):
                text = chunk if isinstance(chunk, str) else ("" if chunk is None else str(chunk))
                if not text:
                    continue
                parts.append(text)
                yield StreamEvent(kind="delta", text=text)
        except Exception as e:  # noqa: BLE001
            err = f"对话出错: {sanitize_exception_message(e)}"
            app.logger.error("对话流式失败: %s", e)
            yield StreamEvent(kind="delta", text=err)
            yield StreamEvent(kind="final", answer=err)
            return

        result = "".join(parts)
        if not result.strip():
            result = "对话出错: 模型返回空内容，请重试或检查 API Key / 模型设置"
            yield StreamEvent(kind="delta", text=result)
            yield StreamEvent(kind="final", answer=result)
            return

        out_ok, out_reason = app.content_filter.check_output(result)
        if not out_ok:
            result = f"[安全拦截] {out_reason}"

        await self._persist(prep, result)
        yield StreamEvent(kind="final", answer=result)

    # 兼容旧名
    async def astream_simple(self, message: str, **kwargs):
        async for ev in self.astream(message, **kwargs):
            if ev.kind == "delta" and ev.text:
                yield ev.text

    async def _run(
        self,
        user_input: str,
        session_id: str = "default",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        active_file: str | None = None,
        files: list | None = None,
    ) -> str:
        app = self._app
        blocked = await app.security.guard(user_input, rate_limit=True)
        if blocked:
            return blocked

        try:
            prep = await self._prepare(
                user_input,
                session_id=session_id,
                api_key=api_key,
                api_base=api_base,
                model_name=model_name,
                active_file=active_file,
                files=files,
            )
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            app.logger.error("对话失败: %s", e)
            return f"对话出错: {sanitize_exception_message(e)}"

        try:
            chain = self._prompt() | prep.llm | StrOutputParser()
            result = chain.invoke(
                {
                    "input": prep.llm_input,
                    "history": prep.history,
                    "summary_block": prep.system_extra,
                }
            )
            if not isinstance(result, str):
                result = "" if result is None else str(result)
            if not result.strip():
                return "对话出错: 模型返回空内容，请重试或检查 API Key / 模型设置"

            out_ok, out_reason = app.content_filter.check_output(result)
            if not out_ok:
                return f"[安全拦截] {out_reason}"

            await self._persist(prep, result)
            return result
        except Exception as e:
            app.logger.error("对话失败: %s", e)
            return f"对话出错: {sanitize_exception_message(e)}"

    async def _prepare(
        self,
        user_input: str,
        *,
        session_id: str,
        api_key: str | None,
        api_base: str | None,
        model_name: str | None,
        active_file: str | None,
        files: list | None,
    ) -> _PreparedTurn:
        app = self._app
        if not active_file and files:
            first = files[0]
            if isinstance(first, dict):
                active_file = first.get("path")
            else:
                active_file = getattr(first, "path", None)

        memory_session_id = session_id
        effective_input = user_input
        skill_extra = ""
        skill_temp: float | None = None
        skill_model: str | None = None
        try:
            (
                effective_input,
                skill_extra,
                memory_session_id,
                _resolved,
                skill_temp,
                skill_model,
            ) = await app._resolve_skill_for_turn(
                user_input,
                session_id,
                active_file=active_file,
            )
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            app.logger.warning("Skills 解析失败，回退普通对话: %s", e)

        from application.prompts.files import build_files_prefix

        files_prefix = build_files_prefix(files)
        llm_input = (
            files_prefix + "用户请求：\n" + effective_input
            if files_prefix
            else effective_input
        )

        llm = app._resolve_llm(
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            temperature=skill_temp,
        )

        if app.memory is None:
            await app.init_session_store()

        summary_block = ""
        history: list = []
        if app.memory is not None:
            turn = await app.memory.load_turn_context(
                memory_session_id, effective_input
            )
            summary_block = turn.system_extra()
            for msg in turn.recent_messages:
                if msg["role"] == "user":
                    history.append(HumanMessage(content=msg.get("content") or ""))
                elif msg["role"] == "assistant":
                    history.append(AIMessage(content=msg.get("content") or ""))

        return _PreparedTurn(
            llm=llm,
            llm_input=llm_input,
            history=history,
            system_extra=(summary_block or "") + (skill_extra or ""),
            memory_session_id=memory_session_id,
            persist_user=user_input,
        )

    async def _persist(self, prep: _PreparedTurn, result: str) -> None:
        app = self._app
        if app.memory is not None:
            memory = app.memory
            await memory.persist_turn(
                session_id=prep.memory_session_id,
                user_input=prep.persist_user,
                assistant_output=result,
            )

            async def _bg_compact() -> None:
                try:
                    await memory.compact_after_turn(
                        session_id=prep.memory_session_id,
                        user_input=prep.persist_user,
                        assistant_output=result,
                    )
                except Exception as exc:  # noqa: BLE001
                    app.logger.warning("后台 Solip/Compact 失败: %s", exc)

            asyncio.create_task(_bg_compact())
        elif app.session_store:
            await app.session_store.add_message(
                prep.memory_session_id, "user", prep.persist_user
            )
            await app.session_store.add_message(
                prep.memory_session_id, "assistant", result
            )

    @staticmethod
    def _prompt() -> ChatPromptTemplate:
        return ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ]
        )
