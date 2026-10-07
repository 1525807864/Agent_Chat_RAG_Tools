"""一次对话运行的领域结果与请求上下文（与 FastAPI / LangChain 解耦）。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class RequestContext:
    """编排层入口上下文：描述「这一轮要干什么」，不含框架对象。"""

    message: str
    mode: str = "chat"
    session_id: str = "default"
    tenant_id: str = "default"
    multi_mode: str = "sequential"
    agent_name: str = "assistant"
    api_key: Optional[str] = None
    api_base: Optional[str] = None
    model_name: Optional[str] = None
    workspace_root: Optional[str] = None
    e2e_base_url: Optional[str] = None
    qa_tenant_id: Optional[str] = None
    files: list | None = None
    active_file: Optional[str] = None
    # Intent Guard 的 SSE 事件队列（编排层创建并 drain；非流式路径为 None）
    task_events: Optional[Any] = None


@dataclass
class RunResult:
    """统一运行结果：API / CLI / 流式收尾都只认这个结构。"""

    answer: str
    meta: dict[str, Any] = field(default_factory=dict)
    traces: list[dict[str, Any]] = field(default_factory=list)

    def with_meta(self, **kwargs: Any) -> RunResult:
        merged = dict(self.meta)
        merged.update(kwargs)
        return RunResult(answer=self.answer, meta=merged, traces=list(self.traces))


@dataclass(frozen=True)
class StreamEvent:
    """流式编排事件：API 只认 kind/text/answer/meta，不接触 LLM 类型。

    kind:
    - "delta"：答案增量
    - "final"：完整答案 + usage meta
    - "task"：意图追踪帧（meta = {"type": anchor|check|plan_update|finalize, "data": ...}）
    """

    kind: str  # "delta" | "final" | "task"
    text: str = ""
    answer: str = ""
    meta: dict[str, Any] = field(default_factory=dict)
