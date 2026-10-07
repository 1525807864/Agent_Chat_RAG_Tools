"""Intent Guard 数据模型：意图锚点 + 任务清单（TaskPlan）。

TaskPlan 是「会话级意图台账」：跨轮累积、带状态机，与 Solip（每轮预测）
并存。进程态为权威，memdir（session-task-plan 条目）与 MySQL（P3 表）为镜像。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# 任务状态机：pending → in_progress → done | blocked | skipped
TASK_PENDING = "pending"
TASK_IN_PROGRESS = "in_progress"
TASK_DONE = "done"
TASK_BLOCKED = "blocked"
TASK_SKIPPED = "skipped"

TASK_TERMINAL = {TASK_DONE, TASK_BLOCKED, TASK_SKIPPED}

TASK_STATUS_CN = {
    TASK_PENDING: "待办",
    TASK_IN_PROGRESS: "进行中",
    TASK_DONE: "已完成",
    TASK_BLOCKED: "已搁置",
    TASK_SKIPPED: "已放弃",
}

# 校验 verdict 白名单（checker 输出不在此列按 error 处理）
ALIGNMENT_VERDICTS = ("aligned", "drift", "irrelevant")
COMPLETION_VERDICTS = ("complete", "partial", "not_started")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_task_id() -> str:
    return "t" + uuid.uuid4().hex[:8]


@dataclass
class Task:
    """任务清单中的一个子任务。"""

    id: str = ""
    title: str = ""
    status: str = TASK_PENDING
    closed_by: str = ""  # check | planner | user
    closed_at: str = ""
    sort: int = 0
    # 依赖的其他任务id 空列表 = 一开始就可以进就绪队列
    depends_on: list[str] = field(default_factory=list)
    # 本条怎样才算完成，给complete_active_task和补全校验当证据标准
    acceptance: str = ""
    # 当前绑着的工具名，例如 web_search；空表示尚未认领
    bound_action: str = ""
    # 本条已经尝试执行几次，超过上限才标 blocked
    attempt: int = 0
    # 最近一次 Observation 摘要，只给人看，不要写进模型 prompt 全文
    evidence: str = ""
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id or new_task_id(),
            "title": self.title,
            "status": self.status,
            "closed_by": self.closed_by,
            "closed_at": self.closed_at,
            "sort": self.sort,
            "depends_on": list(self.depends_on),
            "acceptance": self.acceptance,
            "bound_action": self.bound_action,
            "attempt": self.attempt,
            "evidence": self.evidence,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        status = str(data.get("status") or TASK_PENDING)
        if status not in TASK_STATUS_CN:
            status = TASK_PENDING
        raw_deps = data.get("depends_on") or []
        depends_on = [str(x) for x in raw_deps if str(x).strip()] if isinstance(raw_deps, list) else []
        return cls( 
            id=str(data.get("id") or ""),
            title=str(data.get("title") or "").strip(),
            status=status,
            closed_by=str(data.get("closed_by") or ""),
            closed_at=str(data.get("closed_at") or ""),
            sort=int(data.get("sort") or 0),
            depends_on=depends_on,
            acceptance=str(data.get("acceptance") or ""),
            bound_action=str(data.get("bound_action") or ""),
            attempt=int(data.get("attempt") or 0),
            evidence=str(data.get("evidence") or ""),
        )


@dataclass
class TaskPlan:
    """会话意图台账：锚点 + 任务清单 + 执行统计。"""

    session_id: str = "default"
    goal: str = ""          # 意图锚点（用户首条消息原文，零 LLM 成本）
    goal_raw: str = ""
    turn_created: int = 1
    last_confirmed_turn: int = 0
    anchor_history: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[Task] = field(default_factory=list)
    version: int = 0
    check_errors: int = 0
    drift_count: int = 0
    blocked_actions: int = 0
    last_check: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "session_id": self.session_id,
            "goal": self.goal,
            "goal_raw": self.goal_raw,
            "turn_created": self.turn_created,
            "last_confirmed_turn": self.last_confirmed_turn,
            "anchor_history": list(self.anchor_history),
            "tasks": [t.to_dict() for t in self.tasks],
            "version": self.version,
            "check_errors": self.check_errors,
            "drift_count": self.drift_count,
            "blocked_actions": self.blocked_actions,
            "last_check": dict(self.last_check),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskPlan":
        if not isinstance(data, dict):
            return cls()
        return cls(
            session_id=str(data.get("session_id") or "default"),
            goal=str(data.get("goal") or ""),
            goal_raw=str(data.get("goal_raw") or ""),
            turn_created=int(data.get("turn_created") or 1),
            last_confirmed_turn=int(data.get("last_confirmed_turn") or 0),
            anchor_history=list(data.get("anchor_history") or []),
            tasks=[
                Task.from_dict(t) for t in (data.get("tasks") or []) if isinstance(t, dict)
            ],
            version=int(data.get("version") or 0),
            check_errors=int(data.get("check_errors") or 0),
            drift_count=int(data.get("drift_count") or 0),
            blocked_actions=int(data.get("blocked_actions") or 0),
            last_check=(
                dict(data["last_check"]) if isinstance(data.get("last_check"), dict) else {}
            ),
        )

    def progress(self) -> dict[str, float]:
        """完成进度：done 算 1，in_progress 算 0.5；total 不含 skipped。"""
        total = [t for t in self.tasks if t.status != TASK_SKIPPED]
        score = 0.0
        for t in total:
            if t.status == TASK_DONE:
                score += 1.0
            elif t.status == TASK_IN_PROGRESS:
                score += 0.5
        return {"done": score, "total": float(len(total))}

    def open_tasks(self) -> list[Task]:
        """未闭环任务（pending / in_progress）。"""
        return [t for t in self.tasks if t.status not in TASK_TERMINAL]

    def open_task_dicts(self) -> list[dict[str, Any]]:
        return [t.to_dict() for t in self.open_tasks()]

    def bump(self) -> None:
        self.version += 1

    def human_text(self) -> str:
        """给 memdir 条目用的可读文本（不参与相关性召回，仅审计可读）。"""
        lines = [f"用户目标：{self.goal}"]
        for t in self.tasks:
            lines.append(f"- [{TASK_STATUS_CN.get(t.status, t.status)}] {t.title}")
        return "\n".join(lines)
    def ready_tasks(self) -> list[Task]:
        """依赖都已 done（或没有依赖），且自身还是 pending 的任务。"""
        done_ids = {t.id for t in self.tasks if t.status == TASK_DONE}
        ready: list[Task] = []
        for t in self.tasks:
            if t.status != TASK_PENDING:
                continue
            if all(dep in done_ids for dep in t.depends_on):
                ready.append(t)
        ready.sort(key=lambda x: x.sort)
        return ready

    def active_task(self) -> Task | None:
        """同一时刻只允许一条 in_progress（Cursor 约束）。"""
        for t in self.tasks:
            if t.status == TASK_IN_PROGRESS:
                return t
        return None