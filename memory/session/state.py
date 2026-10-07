"""子系统 C：会话记忆状态（内存对象）。

SessionMemoryState：进程内可续状态（摘要、Solip、槽位）。
TurnContext：单轮装载结果，交给 Chat / Agent 拼 prompt。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from memory.slots import SessionSlots


@dataclass
class TurnContext:
    """装载阶段产出：本轮要喂给模型的上下文材料。"""

    recent_messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    memory_block: str = ""
    next_questions: list[dict[str, Any]] = field(default_factory=list)
    selected_memory_ids: list[str] = field(default_factory=list)
    task_plan: dict[str, Any] | None = None
    slots: SessionSlots | None = None
    # Memory V2：改写后的完整问句（Agent 任务 / 工具搜索用）
    rewritten_query: str = ""
    rewrite_meta: dict[str, Any] = field(default_factory=dict)

    def system_extra(self) -> str:
        """合并进 ChatPrompt / Agent system 的附加段。"""
        parts: list[str] = []
        # 槽位优先：短句跟进时最可靠
        if self.slots and (
            self.slots.location
            or self.slots.preferences
            or self.slots.entities
        ):
            lines = ["【已知用户事实/槽位】（必须优先使用，勿再追问）"]
            if self.slots.location:
                lines.append(f"- 地点: {self.slots.location}")
            if self.slots.timezone:
                lines.append(f"- 时区: {self.slots.timezone}")
            for k, v in self.slots.preferences.items():
                lines.append(f"- {k}: {v}")
            if self.slots.entities:
                lines.append("- 实体: " + "、".join(self.slots.entities[:8]))
            parts.append("\n".join(lines))
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
        if self.task_plan:
            goal = str(self.task_plan.get("goal") or "").strip()
            open_lines: list[str] = []
            for t in self.task_plan.get("tasks") or []:
                if not isinstance(t, dict):
                    continue
                if t.get("status") in ("done", "blocked", "skipped"):
                    continue
                status_cn = "进行中" if t.get("status") == "in_progress" else "待办"
                open_lines.append(f"- [{status_cn}] {t.get('title', '')}")
            if goal or open_lines:
                lines = [f"【当前任务清单】用户目标：{goal or '（无）'}"]
                lines.extend(open_lines[:8])
                lines.append("必须优先完成上述任务，不要偏离目标。")
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
    task_plan: dict[str, Any] | None = None
    slots: SessionSlots = field(default_factory=SessionSlots)
