"""子系统 C：会话记忆状态（内存对象）
SessionMemoryState：一个 session 在进程内的可续状态（摘要、Solip 缓存等）。
TurnContext：单轮装载结果，交给 ask_chat 拼 prompt。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TurnContext:
    """装载阶段产出：本轮要喂给模型的上下文材料。"""

    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    memory_block: str = ""
    next_questions: list[dict[str, Any]] = field(default_factory=list)
    selected_memory_ids: list[str] = field(default_factory=list)

    def system_extra(self) -> str:
        """合并进 ChatPrompt 的 system 附加段。"""
        parts: list[str] = []
        if self.summary:
            parts.append(f"【历史摘要】{self.summary}")
        if self.memory_block:
            parts.append(self.memory_block)
        if self.next_questions:
            lines = ["【Solip 下一问假设】（仅供参考）"]
            for q in self.next_questions[:5]:
                if isinstance(q, dict):
                    lines.append(
                        f"- [{q.get('confidence', '?')}] {q.get('question', '')}"
                    )
                else:
                    lines.append(f"- {q}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)


@dataclass
class SessionMemoryState:
    """进程内会话态缓存（可与 Memdir 双写）。

    进程重启后以 Memdir + session_store 为准重新装载。
    """

    session_id: str
    summary: str = ""
    next_questions: list[dict[str, Any]] = field(default_factory=list)
    intent_hypothesis: str = ""
    open_loops: list[str] = field(default_factory=list)
