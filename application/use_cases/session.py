"""会话读写用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class SessionUseCase:
    """会话列表 / 历史 / 删除 / 记忆快照。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def list_sessions(self) -> list[str]:
        app = self._app
        if not app.session_store:
            await app.init_session_store()
        return await app.session_store.list_sessions()

    async def get_history(self, session_id: str, n: int = 20) -> list[dict]:
        app = self._app
        if not app.session_store:
            await app.init_session_store()
        return await app.session_store.get_recent_messages(session_id, n)

    async def delete_session(self, session_id: str) -> None:
        app = self._app
        if not app.session_store:
            await app.init_session_store()
        await app.session_store.clear_session(session_id)
        if app.memory is not None:
            app.memory.forget_session(session_id)

    def memory_snapshot(self, session_id: str) -> dict:
        app = self._app
        if not app.memory:
            return {
                "session_id": session_id,
                "intent_hypothesis": "",
                "open_loops": [],
                "next_questions": [],
                "summary": "",
            }
        return app.memory.get_solip(session_id)

    async def persist_turn(
        self, session_id: str, user_input: str, assistant_output: str
    ) -> None:
        """编排层（如 Cursor）落库用。"""
        app = self._app
        if app.memory is None:
            await app.init_session_store()
        if app.memory is not None:
            await app.memory.persist_turn(
                session_id=session_id,
                user_input=user_input,
                assistant_output=assistant_output,
            )
        elif app.session_store:
            await app.session_store.add_message(session_id, "user", user_input)
            await app.session_store.add_message(
                session_id, "assistant", assistant_output
            )
