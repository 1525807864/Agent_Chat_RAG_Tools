"""多 Agent 编排器

知识点:
1. Orchestrator = 多 Agent 系统的大脑: 任务分解 → Agent 调度 → 结果汇总
2. 三种协作模式:
   a) Sequential (顺序): A → B → C, 流水线式
   b) Router (路由): 按输入特征分发到最合适的 Agent
   c) Debate (辩论): 多 Agent 轮流发表观点, 最后汇总

边界:
- 最大轮次限制防止死循环
- Agent 不存在时抛出明确错误
- 异常时返回带 execution_log 的失败结果, 而非直接崩溃
"""

import time
from dataclasses import dataclass, field
from agents.base_agent import BaseAgent


@dataclass
class Task:
    """编排器用的任务描述结构（当前 sequential/debate/router 主要以字符串 task 驱动；
    本 dataclass 预留依赖图、状态机等扩展，便于后续做更细粒度调度）。"""

    id: str
    description: str
    assigned_agent: str | None = None
    status: str = "pending"  # pending | running | completed | failed
    result: str | None = None
    dependencies: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class OrchestratorResult:
    """一次编排运行的统一返回结构，供 ``AgentApplication.ask_multi_agent`` 取 final_answer。"""

    success: bool
    final_answer: str
    agent_outputs: dict[str, dict]
    execution_log: list[str]
    total_time_ms: float


class MultiAgentOrchestrator:
    """多 Agent 编排器 — 负责任务分发与结果汇总，不负责单个 Agent 内部的 ReAct 细节。"""

    def __init__(self, name: str = "Orchestrator", max_rounds: int = 3):
        self.name = name
        # name → Agent 实例；register 同名会覆盖，便于重复调用 ask_multi_agent。
        self.agents: dict[str, BaseAgent] = {}
        self.max_rounds = max_rounds

    def register_agent(self, agent: BaseAgent) -> None:
        """注册或覆盖同名 Agent。"""
        self.agents[agent.name] = agent

    def unregister_agent(self, agent_name: str) -> None:
        """按名移除；不存在时静默忽略（pop 默认值）。"""
        self.agents.pop(agent_name, None)

    def get_agent(self, name: str) -> BaseAgent:
        """按名获取 Agent；不存在时抛 ValueError 并附带当前可用名称列表。"""
        agent = self.agents.get(name)
        if not agent:
            raise ValueError(f"未找到 Agent: {name}, 可用: {list(self.agents.keys())}")
        return agent

    # ===== Sequential (顺序执行) =====
    async def run_sequential(
        self, task: str, agent_names: list[str], pass_context: bool = True
    ) -> OrchestratorResult:
        start = time.time()
        log: list[str] = []
        outputs: dict[str, dict] = {}
        context: dict = {}
        final_result = ""

        for i, agent_name in enumerate(agent_names):
            agent = self.get_agent(agent_name)
            if i == 0:
                step_task = task
            else:
                prev = final_result or ""
                step_task = (
                    f"用户原任务: {task}\n\n"
                    f"上一 Agent 的结果（可能含 web_search 内容，请采信其中的链接与摘要）:\n"
                    f"{prev}\n\n"
                    f"请基于以上结果继续处理，不要声称无法联网。"
                )
            log.append(f"[步骤{i+1}] {agent_name}({agent.role}) 开始处理...")

            try:
                result = await agent.run(step_task, context if pass_context else None)
                outputs[agent_name] = result
                if pass_context:
                    context[f"step_{i}"] = result
                final_result = result.get("result", "")
                log.append(f"[步骤{i+1}] {agent_name} 完成")
            except Exception as e:
                log.append(f"[步骤{i+1}] {agent_name} 失败: {e}")
                return OrchestratorResult(
                    success=False, final_answer=str(e),
                    agent_outputs=outputs, execution_log=log,
                    total_time_ms=(time.time() - start) * 1000,
                )

        # 若最后一环结果空洞，回退到 researcher（常有搜索结果）
        if (not (final_result or "").strip()) and "researcher" in outputs:
            final_result = outputs["researcher"].get("result", "") or final_result

        return OrchestratorResult(
            success=True, final_answer=final_result,
            agent_outputs=outputs, execution_log=log,
            total_time_ms=(time.time() - start) * 1000,
        )

    # ===== Router (路由器) =====
    async def run_router(self, task: str, router_agent_name: str) -> OrchestratorResult:
        start = time.time()
        log: list[str] = []
        outputs: dict[str, dict] = {}

        router = self.get_agent(router_agent_name)
        agent_list = "\n".join(
            f"- {name}: {agent.role}"
            for name, agent in self.agents.items() if name != router_agent_name
        )
        route_prompt = (
            f"用户任务: {task}\n\n可用 Agent:\n{agent_list}\n\n"
            f"请只回复最适合处理此任务的 Agent 名称 (只回复一个名称):"
        )

        try:
            route_result = await router.run(route_prompt)
            selected_name = route_result.get("result", "").strip()
            log.append(f"Router 选择了: {selected_name}")

            for name in self.agents:
                if name.lower() in selected_name.lower():
                    selected_name = name
                    break

            agent = self.get_agent(selected_name)
            result = await agent.run(task)
            outputs[selected_name] = result

            return OrchestratorResult(
                success=True, final_answer=result.get("result", ""),
                agent_outputs=outputs, execution_log=log,
                total_time_ms=(time.time() - start) * 1000,
            )
        except Exception as e:
            return OrchestratorResult(
                success=False, final_answer=str(e),
                agent_outputs=outputs, execution_log=log,
                total_time_ms=(time.time() - start) * 1000,
            )

    # ===== Debate (辩论模式) =====
    async def run_debate(
        self, topic: str, agent_names: list[str], rounds: int = 2
    ) -> OrchestratorResult:
        start = time.time()
        log: list[str] = []
        outputs: dict[str, dict] = {}
        all_opinions: list[str] = []

        for r in range(rounds):
            log.append(f"--- 第 {r+1} 轮辩论 ---")
            for agent_name in agent_names:
                agent = self.get_agent(agent_name)
                context_text = "\n".join(all_opinions) if all_opinions else "（首轮发言）"
                debate_task = (
                    f"讨论话题: {topic}\n\n"
                    f"之前的观点:\n{context_text}\n\n"
                    f"请发表你的观点 (可以赞同、反对或补充):"
                )
                result = await agent.run(debate_task)
                opinion = result.get("result", "")
                outputs[f"{agent_name}_round{r+1}"] = result
                all_opinions.append(f"[{agent_name}]: {opinion}")
                log.append(f"  {agent_name}: {opinion[:100]}...")

        # 汇总: 第一个 Agent 总结
        summarizer = self.get_agent(agent_names[0])
        summary_task = (
            f"原始话题: {topic}\n\n所有观点:\n" + "\n".join(all_opinions) +
            "\n\n请总结以上辩论, 给出最终结论和建议:"
        )
        final_result = await summarizer.run(summary_task)

        return OrchestratorResult(
            success=True, final_answer=final_result.get("result", ""),
            agent_outputs=outputs, execution_log=log,
            total_time_ms=(time.time() - start) * 1000,
        )

    # ===== 消息总线 =====
    async def broadcast_message(self, sender: str, msg_type: str, content: str) -> None:
        for name, agent in self.agents.items():
            if name != sender:
                agent.send_message(sender, msg_type, content)
