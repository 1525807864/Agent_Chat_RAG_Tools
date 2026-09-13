"""子系统 D：压缩 + 沉淀（Compact → extract → Memdir）

五层策略：
L1 原始消息在 session_store
L2 滑动窗口（window）
L3 会话摘要（HistoryCompressor）
L4 结构化沉淀（open_loops / intent 写入 Memdir）
L5 Solip 预测（SolipPredictor → Memdir kind=solip）
"""
from __future__ import annotations

from typing import Any

from memory.history_compressor import HistoryCompressor
from memory.memdir.store import MemdirStore
from memory.session.state import SessionMemoryState
from memory.solip.predictor import SolipPredictor


class CompactPipeline:
    def __init__(
        self,
        compressor: HistoryCompressor,
        memdir: MemdirStore,
        solip: SolipPredictor | None,
        *,
        solip_enabled: bool = True,
    ):
        self.compressor = compressor
        self.memdir = memdir
        self.solip = solip
        self.solip_enabled = solip_enabled

    async def after_turn(
        self,
        *,
        session_id: str,
        state: SessionMemoryState,
        all_recent_for_compress: list[dict[str, Any]],
        user_input: str,
        assistant_output: str,
    ) -> SessionMemoryState:
        """一轮对话成功后：可能压缩摘要 + 跑 Solip + 写 Memdir。"""
        summary = state.summary
        window_msgs = all_recent_for_compress

        # L3：HistoryCompressor.should_compress(messages, ...)
        if self.compressor.should_compress(all_recent_for_compress):
            try:
                # 注意：现有 compressor 参数名是 existing_summmary（三层 m）
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
            except Exception:
                pass

        # L5 + L4
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
                        + " | ".join(q["question"] for q in state.next_questions)
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
            except Exception:
                pass

        return state
