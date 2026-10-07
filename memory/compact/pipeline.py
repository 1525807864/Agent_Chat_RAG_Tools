"""子系统 D：压缩 + 沉淀（Compact → Solip → 事实抽取）。

五层 + V2：
L1 原始消息 session_store
L2 滑动窗口
L3 会话摘要 HistoryCompressor
L4 open_loops / intent → Memdir
L5 Solip
V2 事实抽取 → slots + SemanticMemoryStore
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel

from memory.history_compressor import HistoryCompressor
from memory.memdir.store import MemdirStore
from memory.observability import memory_event, memory_warn
from memory.semantic.extractor import extract_memories
from memory.semantic.store import SemanticMemoryStore
from memory.session.state import SessionMemoryState
from memory.slots import SessionSlots
from memory.solip.predictor import SolipPredictor

_log = logging.getLogger(__name__)


class CompactPipeline:
    def __init__(
        self,
        compressor: HistoryCompressor,
        memdir: MemdirStore,
        solip: SolipPredictor | None,
        *,
        solip_enabled: bool = True,
        llm: BaseChatModel | None = None,
        fact_extract_enabled: bool = False,
        semantic_store: SemanticMemoryStore | None = None,
        compress_min_messages: int = 12,
        compress_max_context_tokens: int = 3500,
    ):
        self.compressor = compressor
        self.memdir = memdir
        self.solip = solip
        self.solip_enabled = solip_enabled
        self.llm = llm
        self.fact_extract_enabled = fact_extract_enabled
        self.semantic_store = semantic_store
        self.compress_min_messages = compress_min_messages
        self.compress_max_context_tokens = compress_max_context_tokens

    async def after_turn(
        self,
        *,
        session_id: str,
        state: SessionMemoryState,
        all_recent_for_compress: list[dict[str, Any]],
        user_input: str,
        assistant_output: str,
        tenant_id: str = "default",
    ) -> SessionMemoryState:
        """一轮对话成功后：压缩摘要 + Solip +（可选）事实抽取。"""
        summary = state.summary
        window_msgs = all_recent_for_compress
        if state.slots is None:
            state.slots = SessionSlots()

        # ---- L3 摘要 ----
        if self.compressor.should_compress(
            all_recent_for_compress,
            max_context_tokens=self.compress_max_context_tokens,
            min_messages=self.compress_min_messages,
        ):
            try:
                window_msgs, summary = await self.compressor.compress(
                    all_recent_for_compress,
                    existing_summmary=summary,
                )
                state.summary = summary or state.summary
                if state.summary:
                    self.memdir.upsert_session_item(
                        session_id,
                        kind="summary",
                        text=state.summary,
                        tags=["summary"],
                        score_hint=0.8,
                        item_id="session-summary",
                        meta={},
                    )
                    memory_event(
                        "compact_summary_saved",
                        session_id=session_id,
                        summary_len=len(state.summary),
                    )
            except Exception as e:  # noqa: BLE001
                memory_warn("compact_summary_failed", e, session_id=session_id)

        # ---- L5 + L4 Solip ----
        if self.solip_enabled and self.solip is not None:
            try:
                result = await self.solip.predict(
                    user_input=user_input,
                    assistant_output=assistant_output,
                    recent_messages=window_msgs,
                    summary=state.summary,
                )
                state.intent_hypothesis = result.get("intent_hypothesis") or ""
                state.open_loops = result.get("open_loops") or []
                state.next_questions = result.get("next_questions") or []

                text_lines = []
                if state.intent_hypothesis:
                    text_lines.append(f"意图假设: {state.intent_hypothesis}")
                if state.open_loops:
                    text_lines.append("未闭环: " + "；".join(state.open_loops))
                if state.next_questions:
                    text_lines.append(
                        "下一问候选: "
                        + " | ".join(
                            q["question"]
                            for q in state.next_questions
                            if isinstance(q, dict) and q.get("question")
                        )
                    )

                self.memdir.upsert_session_item(
                    session_id,
                    kind="solip",
                    text="\n".join(text_lines) or "（暂无预测）",
                    tags=["solip", "next_questions"],
                    score_hint=0.9,
                    item_id="session-solip",
                    meta={
                        "intent_hypothesis": state.intent_hypothesis,
                        "open_loops": state.open_loops,
                        "next_questions": state.next_questions,
                    },
                )

                for i, loop in enumerate(state.open_loops[:5]):
                    self.memdir.upsert_session_item(
                        session_id,
                        kind="open_loop",
                        text=loop,
                        tags=["open_loop"],
                        score_hint=0.75,
                        item_id=f"session-open-loop-{i}",
                        meta={},
                    )
                memory_event(
                    "compact_solip_saved",
                    session_id=session_id,
                    open_loops=len(state.open_loops),
                    next_q=len(state.next_questions),
                )
            except Exception as e:  # noqa: BLE001
                memory_warn("compact_solip_failed", e, session_id=session_id)

        # ---- V2 事实抽取 → 槽位 + 语义库 ----
        if self.fact_extract_enabled and self.llm is not None:
            try:
                items = await extract_memories(
                    llm=self.llm,
                    user_input=user_input,
                    assistant_output=assistant_output,
                )
                for it in items:
                    kind = it.get("kind") or "fact"
                    text = str(it.get("text") or "")
                    # 更新槽位（空值不覆盖）
                    if kind == "location" and text:
                        state.slots.merge_from_extraction({"location": text})
                    elif kind == "preference" and text:
                        # 简单拆「key: value」或整段进 generic
                        if ":" in text:
                            k, _, v = text.partition(":")
                            state.slots.merge_from_extraction(
                                {"preferences": {k.strip(): v.strip()}}
                            )
                        else:
                            state.slots.merge_from_extraction(
                                {"preferences": {"note": text}}
                            )
                    elif kind in ("identity", "fact", "goal", "constraint") and text:
                        state.slots.merge_from_extraction({"entities": [text[:40]]})

                    if self.semantic_store is not None and text:
                        self.semantic_store.append(
                            tenant_id=tenant_id,
                            session_id=session_id,
                            text=text,
                            kind=str(kind),
                            importance=float(it.get("importance") or 0.5),
                        )
                memory_event(
                    "compact_facts",
                    session_id=session_id,
                    tenant_id=tenant_id,
                    extracted=len(items),
                    location=state.slots.location or None,
                )
            except Exception as e:  # noqa: BLE001
                memory_warn("compact_facts_failed", e, session_id=session_id)

        return state
