"""MemoryFacade：商业级记忆门面（Working / Episodic / Semantic / Rewrite）。

装载：SessionStore + 摘要 + 槽位 + 混合召回 +（可选）查询改写 → TurnContext
回写：persist_turn → CompactPipeline（摘要 / Solip / 事实抽取）

灰度：v2_enabled=False 时跳过改写与语义召回，行为接近旧版。
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from memory.compact.pipeline import CompactPipeline
from memory.history_compressor import HistoryCompressor
from memory.memdir.store import MemdirStore
from memory.observability import memory_event, memory_span, memory_warn
from memory.query_rewrite import rewrite_user_query
from memory.relevance.filter import RelevanceFilter
from memory.semantic.retriever import HybridMemoryRetriever
from memory.semantic.store import SemanticMemoryStore
from memory.session.state import SessionMemoryState, TurnContext
from memory.session_store import BaseSessionStore
from memory.slots import SessionSlots
from memory.solip.predictor import SolipPredictor

_log = logging.getLogger(__name__)


def _task_plan_human_text(plan: dict[str, Any]) -> str:
    """memdir 条目的人类可读文本（只作审计可读，不进记忆块）。"""
    lines = [f"用户目标：{str(plan.get('goal') or '')}"]
    status_cn = {
        "pending": "待办",
        "in_progress": "进行中",
        "done": "已完成",
        "blocked": "已搁置",
        "skipped": "已放弃",
    }
    for t in plan.get("tasks") or []:
        if isinstance(t, dict) and t.get("title"):
            st = status_cn.get(str(t.get("status") or ""), str(t.get("status") or ""))
            lines.append(f"- [{st}] {t.get('title', '')}")
    return "\n".join(lines)


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
        # ---- Memory V2（商业增强，可灰度）----
        v2_enabled: bool = False,
        query_rewrite_enabled: bool = True,
        fact_extract_enabled: bool = True,
        semantic_store: SemanticMemoryStore | None = None,
        retriever: HybridMemoryRetriever | None = None,
        semantic_top_k: int = 6,
        summary_max_tokens: int = 480,
        compress_min_messages: int = 12,
        compress_max_context_tokens: int = 3500,
    ):
        self.session_store = session_store
        self.llm = llm
        self.window_size = window_size
        self.solip_enabled = solip_enabled
        self.relevance_top_k = relevance_top_k

        self.v2_enabled = bool(v2_enabled)
        self.query_rewrite_enabled = bool(query_rewrite_enabled)
        self.fact_extract_enabled = bool(fact_extract_enabled)
        self.semantic_store = semantic_store
        self.retriever = retriever or HybridMemoryRetriever()
        self.semantic_top_k = semantic_top_k
        self.compress_min_messages = compress_min_messages
        self.compress_max_context_tokens = compress_max_context_tokens

        self.memdir = MemdirStore(root=memdir_root, project_root=project_root)
        self.relevance = RelevanceFilter()
        self.compressor = HistoryCompressor(
            llm=llm,
            window_size=min(10, window_size),
            max_summary_tokens=summary_max_tokens,
        )
        self.solip = (
            SolipPredictor(llm=llm, top_k=solip_top_k) if solip_enabled else None
        )
        self.compact = CompactPipeline(
            compressor=self.compressor,
            memdir=self.memdir,
            solip=self.solip,
            solip_enabled=solip_enabled,
            llm=llm,
            fact_extract_enabled=self.v2_enabled and self.fact_extract_enabled,
            semantic_store=self.semantic_store,
            compress_min_messages=self.compress_min_messages,
            compress_max_context_tokens=self.compress_max_context_tokens,
        )
        self._states: dict[str, SessionMemoryState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

        memory_event(
            "facade_init",
            v2=self.v2_enabled,
            rewrite=self.query_rewrite_enabled,
            fact_extract=self.fact_extract_enabled,
            has_semantic_store=self.semantic_store is not None,
            window_size=self.window_size,
        )

    def _state(self, session_id: str) -> SessionMemoryState:
        if session_id not in self._states:
            st = SessionMemoryState(session_id=session_id, slots=SessionSlots())
            for it in self.memdir.load_session_items(session_id):
                if it.get("id") == "session-solip":
                    meta = it.get("meta") or {}
                    st.next_questions = meta.get("next_questions") or []
                    st.intent_hypothesis = meta.get("intent_hypothesis") or ""
                    st.open_loops = meta.get("open_loops") or []
                if it.get("id") == "session-summary":
                    st.summary = it.get("text") or st.summary
                if it.get("id") == "session-task-plan":
                    meta = it.get("meta")
                    if isinstance(meta, dict) and meta.get("goal"):
                        st.task_plan = meta
                # 商业：槽位从 memdir 恢复（进程重启不丢地点）
                if it.get("id") == "session-slots":
                    meta = it.get("meta")
                    if isinstance(meta, dict):
                        st.slots = SessionSlots.from_dict(meta)
            self._states[session_id] = st
            memory_event(
                "state_hydrate",
                session_id=session_id,
                has_summary=bool(st.summary),
                has_location=bool(st.slots.location),
                has_task_plan=bool(st.task_plan),
            )
        return self._states[session_id]

    def lock_for(self, session_id: str) -> asyncio.Lock:
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def get_task_plan(self, session_id: str) -> dict[str, Any] | None:
        return self._state(session_id).task_plan

    def set_task_plan(self, session_id: str, plan: dict[str, Any]) -> None:
        self._state(session_id).task_plan = plan

    def persist_task_plan(self, session_id: str, plan: dict[str, Any]) -> None:
        st = self._state(session_id)
        st.task_plan = plan
        try:
            self.memdir.upsert_session_item(
                session_id,
                kind="task_plan",
                text=_task_plan_human_text(plan),
                tags=["task_plan"],
                score_hint=0.1,
                meta=plan,
                item_id="session-task-plan",
            )
            memory_event("persist_task_plan", session_id=session_id, ok=True)
        except Exception as e:  # noqa: BLE001
            memory_warn("persist_task_plan_failed", e, session_id=session_id)

    def persist_slots(self, session_id: str) -> None:
        """槽位落盘（memdir 固定条目）。"""
        st = self._state(session_id)
        try:
            self.memdir.upsert_session_item(
                session_id,
                kind="slots",
                text=(
                    f"location={st.slots.location}; "
                    f"prefs={list(st.slots.preferences.keys())}"
                ),
                tags=["slots"],
                score_hint=0.05,
                meta=st.slots.to_dict(),
                item_id="session-slots",
            )
            memory_event(
                "persist_slots",
                session_id=session_id,
                location=st.slots.location or None,
                prefs=len(st.slots.preferences),
            )
        except Exception as e:  # noqa: BLE001
            memory_warn("persist_slots_failed", e, session_id=session_id)

    async def load_turn_context(
        self,
        session_id: str,
        user_input: str,
        *,
        tenant_id: str = "default",
    ) -> TurnContext:
        """装载本轮上下文（含可选查询改写与混合召回）。"""
        with memory_span(
            "load_turn",
            session_id=session_id,
            tenant_id=tenant_id,
            v2=self.v2_enabled,
        ) as span:
            state = self._state(session_id)
            raw = await self.session_store.get_recent_messages(
                session_id, n=max(self.window_size * 2, 40)
            )
            summary = state.summary
            recent = raw[-self.window_size :] if raw else []
            span["raw_messages"] = len(raw)
            span["window"] = len(recent)

            # L3：装载期也可压缩（长会话防爆上下文）
            if self.compressor.should_compress(
                raw,
                max_context_tokens=self.compress_max_context_tokens,
                min_messages=self.compress_min_messages,
            ):
                try:
                    recent, summary = await self.compressor.compress(
                        raw, existing_summmary=summary
                    )
                    state.summary = summary
                    span["compressed_on_load"] = True
                except Exception as e:  # noqa: BLE001
                    memory_warn("load_compress_failed", e, session_id=session_id)
                    recent = raw[-self.window_size :]

            # ---- 查询改写（V2）----
            rewrite = {
                "original": user_input,
                "rewritten": user_input,
                "reason": "v1_disabled",
            }
            if self.v2_enabled and self.query_rewrite_enabled:
                rewrite = await rewrite_user_query(
                    llm=self.llm,
                    user_input=user_input,
                    recent_messages=recent,
                    slots=state.slots.to_dict(),
                    summary=summary or "",
                )
            retrieval_query = rewrite.get("rewritten") or user_input
            span["rewrite_reason"] = rewrite.get("reason")
            span["rewrite_changed"] = rewrite.get("rewritten") != user_input

            # ---- 候选：memdir + 语义 JSONL ----
            candidates = self.memdir.load_project_items() + self.memdir.load_session_items(
                session_id
            )
            candidates = [
                it
                for it in candidates
                if it.get("kind") not in ("task_plan", "slots")
            ]
            if self.v2_enabled and self.semantic_store is not None:
                try:
                    candidates = candidates + self.semantic_store.load_session(
                        tenant_id, session_id
                    )
                except Exception as e:  # noqa: BLE001
                    memory_warn(
                        "semantic_merge_failed",
                        e,
                        session_id=session_id,
                        tenant_id=tenant_id,
                    )

            # ---- 召回：V2 混合；否则旧关键词 ----
            if self.v2_enabled:
                selected = self.retriever.retrieve(
                    retrieval_query,
                    candidates,
                    top_k=max(self.relevance_top_k, self.semantic_top_k),
                )
                # 无命中时回退旧过滤器，避免记忆块全空
                if not selected:
                    selected = self.relevance.select(
                        retrieval_query,
                        candidates,
                        top_k=self.relevance_top_k,
                    )
            else:
                selected = self.relevance.select(
                    user_input, candidates, top_k=self.relevance_top_k
                )
            memory_block = self.relevance.format_for_prompt(selected)
            span["selected"] = len(selected)

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
                task_plan=state.task_plan,
                slots=state.slots,
                rewritten_query=str(rewrite.get("rewritten") or user_input),
                rewrite_meta=dict(rewrite),
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
        memory_event(
            "persist_turn",
            session_id=session_id,
            user_len=len(user_input or ""),
            assistant_len=len(assistant_output or ""),
        )

    async def compact_after_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        assistant_output: str,
        tenant_id: str = "default",
    ) -> SessionMemoryState:
        """Compact / Solip / 事实抽取（可后台执行）。"""
        with memory_span(
            "compact_after_turn",
            session_id=session_id,
            tenant_id=tenant_id,
        ) as span:
            state = self._state(session_id)
            raw = await self.session_store.get_recent_messages(
                session_id, n=max(self.window_size * 2, 40)
            )
            span["messages"] = len(raw)
            state = await self.compact.after_turn(
                session_id=session_id,
                state=state,
                all_recent_for_compress=raw,
                user_input=user_input,
                assistant_output=assistant_output,
                tenant_id=tenant_id,
            )
            # 槽位可能被抽取更新 → 落盘
            self.persist_slots(session_id)
            self._states[session_id] = state
            return state

    async def commit_turn(
        self,
        *,
        session_id: str,
        user_input: str,
        assistant_output: str,
        tenant_id: str = "default",
    ) -> SessionMemoryState:
        await self.persist_turn(
            session_id=session_id,
            user_input=user_input,
            assistant_output=assistant_output,
        )
        return await self.compact_after_turn(
            session_id=session_id,
            user_input=user_input,
            assistant_output=assistant_output,
            tenant_id=tenant_id,
        )

    def get_solip(self, session_id: str) -> dict[str, Any]:
        st = self._state(session_id)
        return {
            "session_id": session_id,
            "intent_hypothesis": st.intent_hypothesis,
            "open_loops": st.open_loops,
            "next_questions": st.next_questions,
            "summary": st.summary,
            "task_plan": st.task_plan or {},
            "slots": st.slots.to_dict() if st.slots else {},
        }

    def forget_session(self, session_id: str) -> None:
        self._states.pop(session_id, None)
        self._locks.pop(session_id, None)
        memory_event("forget_session", session_id=session_id)
