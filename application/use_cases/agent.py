"""单 Agent（ReAct + MCP）用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from agents.react_agent import ReActAgent
from application.prompts.files import build_files_prefix
from application.prompts.react import (
    append_hint,
    coding_assistant_prompt,
    e2e_assistant_prompt,
    general_assistant_prompt,
)
from domain.run import RunResult
from shared.errors import AppError, sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class AgentUseCase:
    """工具环 Agent；含工作区工具、E2E Playwright、通用 MCP / 主动发现。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str,
        *,
        agent_name: str = "assistant",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        workspace_root: Optional[str] = None,
        files: list | None = None,
        active_file: Optional[str] = None,
        e2e_base_url: Optional[str] = None,
        qa_tenant_id: Optional[str] = None,
    ) -> RunResult:
        answer = await self._run(
            message,
            agent_name=agent_name,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            workspace_root=workspace_root,
            files=files,
            active_file=active_file,
            e2e_base_url=e2e_base_url,
            qa_tenant_id=qa_tenant_id,
        )
        return RunResult(answer=answer, meta={"capability": "agent"})

    async def _run(
        self,
        task: str,
        agent_name: str = "assistant",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        workspace_root: str | None = None,
        files: list | None = None,
        active_file: str | None = None,
        e2e_base_url: str | None = None,
        qa_tenant_id: str | None = None,
    ) -> str:
        app = self._app
        blocked = await app.security.guard(task, rate_limit=True)
        if blocked:
            return blocked

        if not active_file and files:
            first = files[0]
            if isinstance(first, dict):
                active_file = first.get("path")
            else:
                active_file = getattr(first, "path", None)

        effective_task = task
        skill_extra = ""
        skill_temp: float | None = None
        skill_model: str | None = None
        resolved = None
        try:
            (
                effective_task,
                skill_extra,
                _sid,
                resolved,
                skill_temp,
                skill_model,
            ) = await app._resolve_skill_for_turn(
                task,
                session_id="agent",
                active_file=active_file,
            )
            if resolved is not None and getattr(resolved.command, "agent", None):
                agent_name = resolved.command.agent  # type: ignore[assignment]
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            app.logger.warning("Skills 解析失败，回退普通 Agent: %s", e)

        llm = app._resolve_llm(
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            temperature=skill_temp,
        )

        locked = (e2e_base_url or "").strip()
        skill_name = ""
        if resolved is not None:
            cmd = getattr(resolved, "command", None)
            skill_name = (getattr(cmd, "name", None) or "").strip()
        e2e_mode = bool(
            locked
            or skill_name == "e2e"
            or (task or "").lstrip().startswith("/e2e")
        )

        system_prompt: str | None = None
        max_calls = 16
        if workspace_root and not e2e_mode:
            system_prompt = coding_assistant_prompt(skill_extra=skill_extra)
        elif skill_extra and not e2e_mode:
            system_prompt = general_assistant_prompt(skill_extra=skill_extra)

        prefix = build_files_prefix(files)
        full_task = prefix + "用户请求：\n" + effective_task

        if e2e_mode:
            from e2e.mcp_playwright import e2e_system_hint, playwright_mcp_session

            hint = e2e_system_hint(
                locked_url=locked or None,
                user=(app.settings.e2e_user or "").strip(),
                password=(app.settings.e2e_password or "").strip(),
            )
            if skill_extra:
                hint = hint + skill_extra
            system_prompt = e2e_assistant_prompt(hint=hint)
            max_calls = 24
            try:
                async with playwright_mcp_session(locked_url=locked or None) as mcp_tools:
                    agent = ReActAgent(
                        name=agent_name,
                        role="E2E测试助手",
                        llm=llm,
                        tools=list(mcp_tools),
                        system_prompt=system_prompt,
                        max_tool_calls=max_calls,
                    )
                    result = await agent.run(full_task)
                    return result.get("result", "无结果")
            except Exception as e:  # noqa: BLE001
                app.logger.error("Playwright MCP 失败: %s", e)
                return f"E2E 启动失败: {sanitize_exception_message(e)}"

        if system_prompt is None:
            system_prompt = general_assistant_prompt()

        ws = workspace_root if not e2e_mode else None
        async with app.tool_gateway.open_act_session(workspace_root=ws) as assembled:
            system_prompt = append_hint(system_prompt, assembled.discovery_hint)
            agent = ReActAgent(
                name=agent_name,
                role="编程助手" if workspace_root else "通用助手",
                llm=llm,
                tools=assembled.tools,
                system_prompt=system_prompt,
                max_tool_calls=max_calls,
            )
            assembled.bind_agent(agent)
            result = await agent.run(full_task)
            return result.get("result", "无结果")
