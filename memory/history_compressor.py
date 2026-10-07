"""对话历史压缩器 — ConversationSummaryBuffer 商业实现。

触发：消息数 ≥ min_messages 或 token ≥ max_context_tokens。
摘要必须保留地点/人名/偏好/未办事项（服务槽位与改写）。
"""

from __future__ import annotations

import logging
import time

import tiktoken
from langchain_core.language_models.chat_models import BaseChatModel

from memory.observability import memory_event, memory_warn

_log = logging.getLogger(__name__)


class HistoryCompressor:
    """用 LLM 摘要窗口外旧消息，控制上下文长度。"""

    def __init__(
        self,
        llm: BaseChatModel,
        window_size: int = 10,
        max_summary_tokens: int = 480,
        encoding_name: str = "cl100k_base",
    ):
        self.llm = llm
        self.window_size = window_size
        self.max_summary_tokens = max_summary_tokens
        try:
            self.encoder = tiktoken.get_encoding(encoding_name)
        except Exception:  # noqa: BLE001
            self.encoder = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, messages: list[dict]) -> int:
        total = 0
        for msg in messages:
            total += len(self.encoder.encode(str(msg.get("content") or "")))
        return total

    def should_compress(
        self,
        messages: list[dict],
        *,
        max_context_tokens: int = 3500,
        min_messages: int | None = None,
    ) -> bool:
        """条数或 token 任一超阈值即压缩（商业：短聊也能滚摘要）。"""
        if not messages:
            return False
        min_m = min_messages if min_messages is not None else max(self.window_size, 12)
        n = len(messages)
        tokens = self.count_tokens(messages)
        by_count = n >= min_m
        by_tokens = tokens >= max_context_tokens
        hit = by_count or by_tokens
        if hit:
            memory_event(
                "compress_should",
                messages=n,
                tokens=tokens,
                min_messages=min_m,
                max_context_tokens=max_context_tokens,
                by_count=by_count,
                by_tokens=by_tokens,
            )
        return hit

    async def compress(
        self,
        messages: list[dict],
        existing_summmary: str = "",
    ) -> tuple[list[dict], str]:
        """返回 (最近窗口消息, 更新后摘要)。参数名保留三层 m 以兼容旧调用。"""
        if len(messages) <= self.window_size:
            return messages, existing_summmary
        t0 = time.perf_counter()
        old_messages = messages[: -self.window_size]
        recent_messages = messages[-self.window_size :]
        summary_prompt = self._build_summary_prompt(old_messages, existing_summmary)
        try:
            from langchain_core.messages import HumanMessage

            # 优先 async，兼容同步 LLM
            if hasattr(self.llm, "ainvoke"):
                resp = await self.llm.ainvoke([HumanMessage(content=summary_prompt)])
            else:
                resp = self.llm.invoke([HumanMessage(content=summary_prompt)])
            content = resp.content if hasattr(resp, "content") else resp
            new_summary = content if isinstance(content, str) else str(content)
            new_summary = self._trim_summary(new_summary)
            memory_event(
                "compress_done",
                ok=True,
                old_msgs=len(old_messages),
                kept=len(recent_messages),
                summary_len=len(new_summary or ""),
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
        except Exception as e:  # noqa: BLE001
            memory_warn(
                "compress_failed",
                e,
                latency_ms=int((time.perf_counter() - t0) * 1000),
            )
            new_summary = existing_summmary
        return recent_messages, new_summary

    def _build_summary_prompt(
        self, old_messages: list[dict], existing_summary: str
    ) -> str:
        dialog_text = "\n".join(
            f"{msg.get('role')}:{msg.get('content', '')}" for msg in old_messages
        )
        return (
            f"将对话压缩为中文摘要（约 {self.max_summary_tokens} token 内）。\n"
            "必须显式保留：地点、时间、人名、用户偏好、未办事项、关键数字。\n"
            "不要写空话。\n"
            f"已有摘要：{existing_summary or '无'}\n"
            f"对话：\n{dialog_text}\n"
            "输出纯文本摘要。"
        )

    def _trim_summary(self, new_summary: str) -> str:
        tokens = self.encoder.encode(new_summary or "")
        if len(tokens) > self.max_summary_tokens:
            tokens = tokens[: self.max_summary_tokens]
            return self.encoder.decode(tokens) + "..."
        return new_summary or ""


def format_message_for_prompt(messages: list[dict], summary: str = "") -> str:
    parts: list[str] = []
    if summary:
        parts.append("【对话历史摘要】")
        parts.append(summary)
        parts.append("")
        parts.append("--- 以下是当前对话 ---")
        parts.append("")
    i = 0
    while i < len(messages):
        msg = messages[i]
        role = msg.get("role", "user")
        content = msg.get("content", "")
        j = i + 1
        while j < len(messages) and messages[j].get("role") == role:
            content += "\n" + (messages[j].get("content") or "")
            j += 1
        parts.append(f"{role}:{content}")
        i = j
    return "\n".join(parts)
