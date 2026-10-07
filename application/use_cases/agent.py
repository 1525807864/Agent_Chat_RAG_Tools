"""单 Agent（ReAct + MCP）用例。"""

from __future__ import annotations

# asyncio：跑完一轮后后台 compact / Solip，不阻塞先返回答案
import asyncio
from typing import TYPE_CHECKING, Optional

from agents.react_agent import ReActAgent
from application.prompts.files import build_files_prefix
from application.prompts.react import (
    append_hint,
    coding_assistant_prompt,
    e2e_assistant_prompt,
    general_assistant_prompt,
)
from billing.turn_helper import safe_record_turn
from domain.run import RunResult
from domain.usage import TurnUsage
from shared.errors import AppError, sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class AgentUseCase:
    """工具环 Agent；含工作区工具、E2E Playwright、通用 MCP / 主动发现。"""

    def __init__(self, app: AgentApplication) -> None:
        # 持有应用门面：LLM、memory、tool_gateway、settings 都从这里拿
        self._app = app

    async def execute(
        self,
        message: str,                          # 用户本轮输入
        *,
        session_id: str = "default",           # ★ 与前端/chat 同一会话键
        tenant_id: str = "default",            # 计费租户
        agent_name: str = "assistant",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
        workspace_root: Optional[str] = None,
        files: list | None = None,
        active_file: Optional[str] = None,
        e2e_base_url: Optional[str] = None,
        qa_tenant_id: Optional[str] = None,
        task_events=None,                      # Intent Guard SSE 事件队列
    ) -> RunResult:
        # _run 负责真正推理；这里只记账 + 包成 RunResult
        answer, usage_dict, intent_meta = await self._run(
            message,
            session_id=session_id,             # ★ 往下传，不要再丢掉
            tenant_id=tenant_id,               # ★ 审计 / 计费租户
            agent_name=agent_name,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            workspace_root=workspace_root,
            files=files,
            active_file=active_file,
            e2e_base_url=e2e_base_url,
            qa_tenant_id=qa_tenant_id,
            task_events=task_events,
        )
        usage_meta: dict = {}
        if usage_dict:
            # 把 Agent 内部累加的 token 写成领域 TurnUsage，再记入 ledger
            turn = TurnUsage(
                tokens_in=int(usage_dict.get("tokens_in") or 0),
                tokens_out=int(usage_dict.get("tokens_out") or 0),
                requests=int(usage_dict.get("requests") or 1),
                model=str(usage_dict.get("model") or ""),
            )
            usage_meta = safe_record_turn(self._app, tenant_id, turn)
        return RunResult(
            answer=answer,
            meta={"capability": "agent", **usage_meta, **intent_meta},
        )

    async def _run(
        self,
        task: str,
        agent_name: str = "assistant",
        *,
        session_id: str = "default",           # ★ 真实会话 id
        tenant_id: str = "default",            # ★ 审计租户
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        workspace_root: str | None = None,
        files: list | None = None,
        active_file: str | None = None,
        e2e_base_url: str | None = None,
        qa_tenant_id: str | None = None,
        task_events=None,                      # Intent Guard SSE 事件队列
    ) -> tuple[str, dict | None, dict]:
        app = self._app
        import time

        t0 = time.perf_counter()

        # 安全护栏：限流 / 注入检测等，命中则直接返回提示、不调 LLM
        blocked = await app.security.guard(task, rate_limit=False)
        if blocked:
            return blocked, None, {}

        # 没指定 active_file 时，用附件列表第一个路径（给 Skills 用）
        if not active_file and files:
            first = files[0]
            if isinstance(first, dict):
                active_file = first.get("path")
            else:
                active_file = getattr(first, "path", None)

        # ---------- Skills 解析（用真实 session_id，不要写死 "agent"）----------
        effective_task = task
        skill_extra = ""
        skill_temp: float | None = None
        skill_model: str | None = None
        resolved = None
        memory_session_id = session_id         # Skills 可能改成隔离会话 id
        try:
            (
                effective_task,                # 可能被 skill 改写过的用户话
                skill_extra,                   # 拼进 system 的 skill 说明
                memory_session_id,             # skill 可能返回独立 session
                resolved,                      # 解析到的 skill 命令对象
                skill_temp,                    # skill 指定温度
                skill_model,                   # skill 指定模型
            ) = await app._resolve_skill_for_turn(
                task,
                session_id,                    # ★ 用前端会话，不再用 "agent"
                active_file=active_file,
            )
            # skill 可指定换一个 agent 名字（展示/日志用）
            if resolved is not None and getattr(resolved.command, "agent", None):
                agent_name = resolved.command.agent  # type: ignore[assignment]
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            app.logger.warning("Skills 解析失败，回退普通 Agent: %s", e)

        # ---------- 确保 MemoryFacade / SessionStore 已初始化 ----------
        if app.memory is None:
            await app.init_session_store()

        # ---------- 装载本会话历史 + memdir 摘要（和 chat 同一套）----------
        memory_extra = ""                      # 塞进 system 的【历史摘要】【记忆块】
        history_dicts: list[dict] = []         # [{role, content}, ...] 给 ReAct 拼消息
        agent_task = effective_task            # V2 可能改成 rewritten_query
        rewrite_meta: dict = {}
        if app.memory is not None:
            # load_turn_context：读 session_store + 槽位 +（V2）查询改写 / 混合召回
            turn_ctx = await app.memory.load_turn_context(
                memory_session_id,
                effective_task,
                tenant_id=tenant_id,
            )
            memory_extra = turn_ctx.system_extra() or ""
            history_dicts = list(turn_ctx.recent_messages or [])
            # ★ 商业：Agent「任务」用改写后的完整句；落库仍用用户原文 task
            if getattr(turn_ctx, "rewritten_query", None):
                agent_task = turn_ctx.rewritten_query
            rewrite_meta = dict(getattr(turn_ctx, "rewrite_meta", None) or {})
            app.logger.info(
                "memory.load session=%s tenant=%s rewrite=%s changed=%s hist=%s",
                memory_session_id,
                tenant_id,
                rewrite_meta.get("reason"),
                agent_task != effective_task,
                len(history_dicts),
            )

        # ---------- 解析 LLM（skill 模型优先）----------
        llm = app._resolve_llm(
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            temperature=skill_temp,
        )

        # ---------- 意图守卫（目标对齐检查 + 任务完整性维护） ----------
        # 失败 / 关闭时 guard=None，Agent 行为与旧版完全一致（fail-open）
        guard = app.intent_guard_for(
            session_id=memory_session_id,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            event_sink=task_events,
        )
        if guard is not None:
            try:
                await guard.ensure_anchor(user_input=task)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("意图守卫锚点建立失败，本回合关闭: %s", e)
                guard = None

        # ---------- 是否走 E2E Playwright ----------
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

        # ---------- 拼 system prompt ----------
        system_prompt: str | None = None
        max_calls = 16
        if workspace_root and not e2e_mode:
            system_prompt = coding_assistant_prompt(skill_extra=skill_extra)
        elif skill_extra and not e2e_mode:
            system_prompt = general_assistant_prompt(skill_extra=skill_extra)

        # ★ 把 Memory 摘要 / memdir / Solip 接到 system 后面
        # 这样「用户说过北京」会进摘要或 recent，不必靠模型猜
        _CTX_RULE = (
            "\n\n【会话上下文规则】\n"
            "1. 上方/下方若出现【历史摘要】或【相关记忆】或对话历史，必须优先使用，"
            "不要重复追问已提供的信息（如城市、日期、偏好）。\n"
            "2. 用户说「今天有雨吗」「继续」等短句时，结合历史补全省略主语。\n"
            "3. 只有历史里确实没有的信息，才允许追问。\n"
        )
        if memory_extra:
            # memory_extra 已含【历史摘要】【记忆块】等，再拼规则
            memory_block_for_prompt = "\n\n" + memory_extra + _CTX_RULE
        else:
            memory_block_for_prompt = _CTX_RULE

        # 附件路径前缀 + 本轮用户话（V2：agent_task 可能已补全省略主语）
        prefix = build_files_prefix(files)
        full_task = prefix + "用户请求：\n" + agent_task

        # 传给 ReActAgent.run / think 的上下文：历史 +（循环中会加 Observation）
        run_context: dict = {
            "history": history_dicts,          # ★ 多轮对话
            "session_id": memory_session_id,   # 日志/调试用
            "intent_guard": guard,             # 意图守卫（None=关闭）
            # ★ 强制搜索 / 工具 query 优先用改写句，避免「今天有雨吗」丢地点
            "search_query": agent_task,
            "rewrite_meta": rewrite_meta,
        }

        async def _finalize_intent(answer: str) -> tuple[str, dict]:
            """回合后完成度校验：闭环子任务；按需追加未完成清单。

            返回 (最终答案, intent_meta)（intent_meta 含 task_plan 快照）。
            """
            if guard is None:
                return answer, {}
            return await guard.close_turn(user_input=task, answer=answer)

        async def _persist_answer(answer: str, result: dict | None = None) -> None:
            """推理成功后：落库本轮 user/assistant，并后台 compact + 审计。"""
            if app.memory is not None:
                await app.memory.persist_turn(
                    session_id=memory_session_id,
                    user_input=task,           # 存用户原始输入（不是改写后的）
                    assistant_output=answer,
                )

                async def _bg() -> None:
                    try:
                        await app.memory.compact_after_turn(
                            session_id=memory_session_id,
                            user_input=task,
                            assistant_output=answer,
                            tenant_id=tenant_id,
                        )
                    except Exception as exc:  # noqa: BLE001
                        app.logger.warning("后台 Solip/Compact 失败: %s", exc)

                asyncio.create_task(_bg())
            elif app.session_store:
                await app.session_store.add_message(
                    memory_session_id, "user", task
                )
                await app.session_store.add_message(
                    memory_session_id, "assistant", answer
                )

            # P1：审计落库（失败忽略）
            try:
                from infrastructure.db.agent_audit import safe_record_run

                usage = (result or {}).get("usage") if isinstance(result, dict) else None
                usage = usage if isinstance(usage, dict) else {}
                safe_record_run(
                    tenant_id=tenant_id,
                    session_id=memory_session_id,
                    mode="agent",
                    model=str(
                        usage.get("model")
                        or getattr(llm, "model_name", "")
                        or model_name
                        or ""
                    ),
                    status="ok",
                    answer=answer,
                    tokens_in=int(usage.get("tokens_in") or 0),
                    tokens_out=int(usage.get("tokens_out") or 0),
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                    tool_calls=(
                        result.get("tool_calls") if isinstance(result, dict) else None
                    ),
                )
            except Exception:  # noqa: BLE001
                app.logger.warning("agent_runs 写入失败", exc_info=True)

        # ---------- E2E 分支（同样注入 memory + history）----------
        if e2e_mode:
            from e2e.mcp_playwright import e2e_system_hint, playwright_mcp_session

            hint = e2e_system_hint(
                locked_url=locked or None,
                user=(app.settings.e2e_user or "").strip(),
                password=(app.settings.e2e_password or "").strip(),
            )
            if skill_extra:
                hint = hint + skill_extra
            system_prompt = e2e_assistant_prompt(hint=hint) + memory_block_for_prompt
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
                    result = await agent.run(full_task, run_context)
                    usage = result.get("usage") if isinstance(result, dict) else None
                    answer = result.get("result", "无结果")
                    answer, intent_meta = await _finalize_intent(answer)
                    await _persist_answer(answer, result if isinstance(result, dict) else None)
                    return answer, usage if isinstance(usage, dict) else None, intent_meta
            except Exception as e:  # noqa: BLE001
                app.logger.error("Playwright MCP 失败: %s", e)
                try:
                    from infrastructure.db.agent_audit import safe_record_run

                    safe_record_run(
                        tenant_id=tenant_id,
                        session_id=memory_session_id,
                        mode="agent",
                        status="error",
                        answer="",
                        error_message=str(e),
                        latency_ms=int((time.perf_counter() - t0) * 1000),
                    )
                except Exception:  # noqa: BLE001
                    pass
                return f"E2E 启动失败: {sanitize_exception_message(e)}", None, {}

        # ---------- 普通 / 编程 Agent ----------
        if system_prompt is None:
            system_prompt = general_assistant_prompt()
        # ★ 追加记忆块 + 上下文规则（E2E 分支上面已加过）
        system_prompt = system_prompt + memory_block_for_prompt

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
            # ★ 第二参数 context：带 history，think() 会读
            result = await agent.run(full_task, run_context)
            usage = result.get("usage") if isinstance(result, dict) else None
            answer = result.get("result", "无结果")
            answer, intent_meta = await _finalize_intent(answer)
            await _persist_answer(answer, result if isinstance(result, dict) else None)
            return (
                answer,
                usage if isinstance(usage, dict) else None,
                intent_meta,
            )