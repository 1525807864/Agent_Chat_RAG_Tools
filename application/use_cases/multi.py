"""多智能体协作用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from domain.run import RunResult

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class MultiAgentUseCase:
    """sequential / debate / router 多 Agent 图。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str,
        *,
        multi_mode: str = "sequential",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        use_tool_calling: bool = True,
    ) -> RunResult:
        result = await self._run(
            message,
            mode=multi_mode,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            use_tool_calling=use_tool_calling,
        )
        return RunResult(
            answer=str(result.get("final_answer") or ""),
            meta={
                "capability": "multi",
                "execution_log": result.get("execution_log", []),
                "agent_outputs": result.get("agent_outputs", {}),
                "total_time_ms": result.get("total_time_ms"),
                "success": result.get("success"),
            },
        )

    async def _run(
        self,
        task: str,
        mode: str = "sequential",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        use_tool_calling: bool = True,
    ) -> dict:
        from agents.orchestrator import MultiAgentOrchestrator
        from agents.react_agent import RESEARCHER_SYSTEM_PROMPT, ReActAgent
        from agents.tool_calling_agent import ToolCallingAgent
        from billing.usage import LEDGER
        from infrastructure.llm.openai_compat import create_chat_openai
        from observability.tracing import trace

        app = self._app
        blocked = await app.security.guard(task, rate_limit=True)
        if blocked:
            return {
                "final_answer": blocked,
                "execution_log": [],
                "agent_outputs": {},
                "total_time_ms": 0,
                "success": False,
            }

        key = (api_key or "").strip() or (app.settings.deepseek_api_key or "").strip()
        base = (api_base or "").strip() or (app.settings.deepseek_api_base or "").strip()
        model = (model_name or "").strip() or (app.settings.model_name or "").strip()

        orch = MultiAgentOrchestrator()
        web = app.tool_registry.get_tool("web_search")
        read = app.tool_registry.get_tool("read_file")
        code = app.tool_registry.get_tool("execute_python")

        agents_ready = False
        if use_tool_calling and key and base:
            try:
                tc_llm = create_chat_openai(
                    api_key=key,
                    api_base=base,
                    model=model,
                    temperature=app.settings.model_temperature,
                    max_tokens=app.settings.model_max_tokens,
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="researcher",
                        role="信息研究员",
                        llm=tc_llm,
                        tools=[t for t in [web] if t],
                        system_prompt=RESEARCHER_SYSTEM_PROMPT
                        or "你是信息研究员，需要时调用 web_search。",
                    )
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="coder",
                        role="程序员",
                        llm=tc_llm,
                        tools=[t for t in [read, code] if t],
                        system_prompt="你是程序员，优先用工具读文件/执行代码。",
                    )
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="reviewer",
                        role="代码审查员",
                        llm=tc_llm,
                        tools=[t for t in [read] if t],
                        system_prompt="你是代码审查员，基于证据给出审查意见。",
                    )
                )
                agents_ready = True
            except Exception as e:  # noqa: BLE001
                app.logger.warning("tool calling 初始化失败，回退 ReAct: %s", e)

        if not agents_ready:
            llm = app._resolve_llm(
                api_key=api_key, api_base=api_base, model_name=model_name
            )
            orch.register_agent(
                ReActAgent(
                    name="researcher",
                    role="信息研究员",
                    llm=llm,
                    tools=[t for t in [web] if t],
                    system_prompt=RESEARCHER_SYSTEM_PROMPT,
                    max_tool_calls=6,
                )
            )
            orch.register_agent(
                ReActAgent(
                    name="coder",
                    role="程序员",
                    llm=llm,
                    tools=[t for t in [read, code] if t],
                )
            )
            orch.register_agent(
                ReActAgent(
                    name="reviewer",
                    role="代码审查员",
                    llm=llm,
                    tools=[t for t in [read] if t],
                )
            )

        from agents.graphs.multi_agent_graph import run_multi_agent_graph

        result = await run_multi_agent_graph(
            orch.agents,
            task,
            mode=mode,
            debate_rounds=2,
        )

        LEDGER.add("default", requests=1)
        trace("multi_agent", mode=mode, success=result.success)

        outputs: dict = {}
        for name, raw in (result.agent_outputs or {}).items():
            if isinstance(raw, dict):
                outputs[name] = {
                    "result": raw.get("result"),
                    "trace": raw.get("trace", []),
                }
            else:
                outputs[name] = {"result": str(raw), "trace": []}

        return {
            "final_answer": result.final_answer,
            "execution_log": list(result.execution_log or []),
            "agent_outputs": outputs,
            "total_time_ms": result.total_time_ms,
            "success": result.success,
        }
