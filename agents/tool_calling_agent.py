"""P2: 原生 tool calling Agent（OpenAI 兼容 tools 协议）。

依赖 ``langchain_openai.ChatOpenAI`` 的 ``bind_tools``；
DeepSeek 等兼容 Base 在支持 tools 的模型上可用。
"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from billing.turn_helper import empty_turn, merge_message


class ToolCallingAgent:
    """基于 bind_tools 的多轮工具调用 Agent。"""

    def __init__(
        self,
        name: str,
        llm: Any,
        tools: list,
        system_prompt: str,
        max_rounds: int = 8,
        role: str = "",
    ) -> None:
        self.name = name
        self.role = role or name
        self.tools = {t.name: t for t in tools}
        self.llm = llm.bind_tools(tools) if tools else llm
        self.system_prompt = system_prompt
        self.max_rounds = max_rounds
        self.trace: list[dict[str, Any]] = []

    async def run(self, task: str, context: dict | None = None) -> dict:
        """返回 ``{"result": str, "trace": list, "usage": dict}``。

        context["intent_guard"]（可选）：意图守卫。drift 的工具调用不执行，
        用 ToolMessage 回填纠正，保持 bind_tools 协议完整。
        """
        messages: list = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=task),
        ]
        # bind_tools 后的 runnable 可能没有 model_name，尽量从底层读
        model_str = str(
            getattr(self.llm, "model_name", None)
            or getattr(getattr(self.llm, "bound", None), "model_name", None)
            or ""
        )
        usage_acc = empty_turn(model=model_str)
        guard = (context or {}).get("intent_guard")

        for round_no in range(self.max_rounds):
            ai = await self._ainvoke(messages)
            usage_acc = merge_message(usage_acc, ai, model=model_str)
            messages.append(ai)
            tool_calls = getattr(ai, "tool_calls", None) or []
            self.trace.append(
                {
                    "type": "llm",
                    "content": ai.content if isinstance(ai.content, str) else str(ai.content),
                    "tool_calls": tool_calls,
                }
            )

            if not tool_calls:
                text = ai.content if isinstance(ai.content, str) else str(ai.content or "")
                self.trace.append({"type": "final", "text": text})
                return {
                    "result": text,
                    "trace": list(self.trace),
                    "usage": usage_acc.to_dict(),
                }

            for call in tool_calls:
                name = call.get("name") if isinstance(call, dict) else getattr(call, "name", "")
                args = call.get("args") if isinstance(call, dict) else getattr(call, "args", {})
                call_id = (
                    call.get("id")
                    if isinstance(call, dict)
                    else getattr(call, "id", name or "tool")
                )

                blocked = False
                if guard is not None and name:
                    check = await guard.check_step(
                        task=task,
                        iteration=round_no,
                        thought=(
                            ai.content
                            if isinstance(ai.content, str)
                            else str(ai.content or "")
                        ),
                        action_name=name,
                        action_input=(args or {}),
                    )
                    if check.get("_msg") is not None:
                        usage_acc = merge_message(usage_acc, check["_msg"], model=model_str)
                    if check.get("verdict") == "drift":
                        blocked = True
                        self.trace.append(
                            {
                                "type": "tool",
                                "name": name,
                                "args": args,
                                "blocked_by_intent": True,
                                "reason": check.get("reason", ""),
                            }
                        )

                if blocked:
                    out_str = (
                        "[目标对齐拦截] "
                        + str(
                            check.get("correction")
                            or check.get("reason")
                            or "请回到用户最初的目标继续执行"
                        )
                    )
                else:
                    if guard is not None and name:
                        try:
                            guard.claim_task(action_name=name)
                        except Exception:  # noqa: BLE001
                            pass
                    tool = self.tools.get(name or "")
                    if tool is None:
                        out_str = f"未知工具: {name}"
                        if guard is not None:
                            try:
                                guard.complete_active_task(
                                    ok=False, evidence=out_str
                                )
                            except Exception:  # noqa: BLE001
                                pass
                    else:
                        out_str = str(await self._invoke_tool(tool, args or {}))
                        if guard is not None:
                            try:
                                ok = bool(out_str.strip()) and not out_str.startswith(
                                    "未知工具"
                                )
                                guard.complete_active_task(
                                    ok=ok, evidence=out_str[:400]
                                )
                            except Exception:  # noqa: BLE001
                                pass
                    self.trace.append(
                        {
                            "type": "tool",
                            "name": name,
                            "args": args,
                            "output": out_str[:2000],
                        }
                    )
                messages.append(
                    ToolMessage(content=out_str, tool_call_id=str(call_id or name))
                )

        return {
            "result": "达到最大工具调用轮次",
            "trace": list(self.trace),
            "usage": usage_acc.to_dict(),
        }

    async def _ainvoke(self, messages: list) -> AIMessage:
        if hasattr(self.llm, "ainvoke"):
            return await self.llm.ainvoke(messages)
        return await asyncio.to_thread(self.llm.invoke, messages)

    async def _invoke_tool(self, tool: Any, args: dict) -> Any:
        if hasattr(tool, "ainvoke"):
            return await tool.ainvoke(args)
        return await asyncio.to_thread(tool.invoke, args)
