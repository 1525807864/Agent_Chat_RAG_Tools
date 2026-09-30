"""MemoryFacade：四子系统门面

装载：SessionStore 消息 + Memdir 筛选 + Session 态 → TurnContext
回写：写 SessionStore 消息后 → CompactPipeline（摘要 / Solip / 沉淀）
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from memory.compact.pipeline import CompactPipeline
from memory.history_compressor import HistoryCompressor
from memory.memdir.store import MemdirStore
from memory.relevance.filter import RelevanceFilter
from memory.session.state import SessionMemoryState, TurnContext
from memory.session_store import BaseSessionStore
from memory.solip.predictor import SolipPredictor


class MemoryFacade:
    def __init__(
        self,
        *,
        session_store: BaseSessionStore,
        llm: BaseChatModel,
        project_root: Path,
        window_size: int = 20,
        solip_enabled: bool = True,
        solip_top_k: int = 3,
        relevance_top_k: int = 6,
        memdir_root: Path | None = None,
    ):
        self.session_store = session_store
        self.window_size = window_size
        self.solip_enabled = solip_enabled
        self.relevance_top_k = relevance_top_k

        self.memdir = MemdirStore(root=memdir_root, project_root=project_root)
        self.relevance = RelevanceFilter()
        self.compressor = HistoryCompressor(
            llm=llm, window_size=min(10, window_size)
        )
        self.solip = (
            SolipPredictor(llm=llm, top_k=solip_top_k) if solip_enabled else None
        )
        self.compact = CompactPipeline(
            compressor=self.compressor,
            memdir=self.memdir,
            solip=self.solip,
            solip_enabled=solip_enabled,
        )
        self._states: dict[str, SessionMemoryState] = {}

    def _state(self, session_id: str) -> SessionMemoryState:
        if session_id not in self._states:
            st = SessionMemoryState(session_id=session_id)
            for it in self.memdir.load_session_items(session_id):
                if it.get("id") == "session-solip":
                    meta = it.get("meta") or {}
                    st.next_questions = meta.get("next_questions") or []
                    st.intent_hypothesis = meta.get("intent_hypothesis") or ""
                    st.open_loops = meta.get("open_loops") or []
                if it.get("id") == "session-summary":
                    st.summary = it.get("text") or st.summary
            self._states[session_id] = st
        return self._states[session_id]

    async def load_turn_context(self, session_id: str, user_input: str) -> TurnContext:
        """装载阶段：拼本轮上下文。"""
        state = self._state(session_id)
        raw = await self.session_store.get_recent_messages(
            session_id, n=max(self.window_size * 2, 40)
        )

        summary = state.summary
        recent = raw[-self.window_size :] if raw else []

        if self.compressor.should_compress(raw):
            try:
                recent, summary = await self.compressor.compress(
                    raw, existing_summmary=summary
                )
                state.summary = summary
            except Exception:
                recent = raw[-self.window_size :]

        candidates = self.memdir.load_project_items() + self.memdir.load_session_items(
            session_id
        )
        selected = self.relevance.select(
            user_input, candidates, top_k=self.relevance_top_k
        )
        memory_block = self.relevance.format_for_prompt(selected)

        next_qs = state.next_questions
        for it in selected:
            if it.get("kind") == "solip":
                next_qs = (it.get("meta") or {}).get("next_questions") or next_qs

        return TurnContext(
            recent_messages=recent,
            summary=state.summary or summary or "",
            memory_block=memory_block,
            next_questions=next_qs,
            selected_memory_ids=[str(it.get("id")) for it in selected],
        )

    async def persist_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        assistant_output: str,
    ) -> None:
        """只落库本轮消息（不跑 Solip，便于先把答案返回前端）。"""
        await self.session_store.add_message(session_id, "user", user_input)
        await self.session_store.add_message(session_id, "assistant", assistant_output)

    async def compact_after_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        assistant_output: str,
    ) -> SessionMemoryState:
        """Compact / Solip / Memdir 沉淀（可后台执行）。"""
        state = self._state(session_id)
        raw = await self.session_store.get_recent_messages(
            session_id, n=max(self.window_size * 2, 40)
        )
        state = await self.compact.after_turn(
            session_id=session_id,
            state=state,
            all_recent_for_compress=raw,
            user_input=user_input,
            assistant_output=assistant_output,
        )
        self._states[session_id] = state
        return state

    async def commit_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        assistant_output: str,
    ) -> SessionMemoryState:
        """运行后回写：消息落库 + Compact/Solip/沉淀。"""
        await self.persist_turn(
            session_id=session_id,
            user_input=user_input,
            assistant_output=assistant_output,
        )
        return await self.compact_after_turn(
            session_id=session_id,
            user_input=user_input,
            assistant_output=assistant_output,
        )

    def get_solip(self, session_id: str) -> dict[str, Any]:
        """给 HTTP 接口用的只读快照。"""
        st = self._state(session_id)
        return {
            "session_id": session_id,
            "intent_hypothesis": st.intent_hypothesis,
            "open_loops": st.open_loops,
            "next_questions": st.next_questions,
            "summary": st.summary,
        }

    def forget_session(self, session_id: str) -> None:
        """清除进程内会话态（与 session_store.clear_session / 归档删除配套）。

        注意：_states 只是缓存；权威在 chat_messages + memdir 文件/MySQL。
        """
        self._states.pop(session_id, None)
