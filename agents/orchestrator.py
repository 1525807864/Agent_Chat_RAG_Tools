"""多 Agent 注册容器。

协作调度已迁到 ``agents.graphs.multi_agent_graph``；本模块只保留：
- Agent 字典（按 name 注册）
- ``OrchestratorResult``（图运行结果，供 ``ask_multi_agent`` 使用）
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class OrchestratorResult:
    """一次编排运行的统一返回结构，供 ``AgentApplication.ask_multi_agent`` 取 final_answer。"""

    success: bool
    final_answer: str
    agent_outputs: dict[str, dict]
    execution_log: list[str]
    total_time_ms: float


class MultiAgentOrchestrator:
    """按名存放本轮请求的 Agent 实例，交给 LangGraph 调度。"""

    def __init__(self) -> None:
        self.agents: dict[str, Any] = {}

    def register_agent(self, agent: Any) -> None:
        """注册或覆盖同名 Agent。"""
        self.agents[agent.name] = agent
