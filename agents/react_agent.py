"""ReAct Agent 实现

知识点:
1. ReAct = Reasoning + Acting (Yao et al., 2022)
   - Thought: 分析当前情况, 决定下一步
   - Action: 调用工具
   - Observation: 工具返回结果
   - 循环直到 Final Answer

2. ReAct vs Chain-of-Thought: ReAct 多了"行动"能力, 可查询外部信息
3. 工具调用硬边界: max_tool_calls 防止无限循环消耗费用
"""

from __future__ import annotations

from billing.turn_helper import empty_turn, merge_message  # 累加器
import json
import logging
import re
from typing import Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from agents.base_agent import BaseAgent

_log = logging.getLogger(__name__)

REACT_SYSTEM_PROMPT = """你是一个使用 ReAct 框架的智能助手。你可以使用以下工具:

{tools_description}

请按以下格式响应:

需要工具时:
Thought: [分析]
Action: [工具名称]
Action Input: [必须是 JSON 对象，例如 {{"query": "关键词"}}]

不需要工具时（问候、常识、简单计算说明等）:
Thought: 不需要工具
Final Answer: [直接回答用户]

系统会返回 Observation。你可以重复 Thought/Action/Action Input。

当已有足够 Observation 时:
Thought: 我已收集到足够信息
Final Answer: [最终答案]

规则:
1. 每次只调用一个工具
2. Action Input 必须是有效 JSON
3. 不要编造 Observation 中没有的信息
4. 仅当需要实时联网信息（新闻/股价/天气等）且工具列表含 web_search 时，才 Action: web_search
5. 不需要工具时禁止编造 Action，必须直接 Final Answer
"""

RESEARCHER_SYSTEM_PROMPT = """你是信息研究员（researcher），必须使用 ReAct + 工具查证。

可用工具:
{tools_description}

【强制】
1. 用户问行情、股价、纳斯达克、新闻、天气、或任何需要上网的事实时：第一轮必须输出：
Thought: 需要联网搜索
Action: web_search
Action Input: {{"query": "简洁的中文或英文搜索词"}}
2. 禁止说「无法联网」「模拟工具」「请自行打开 Yahoo/Google」——你有 web_search。
3. 只有在 Observation 返回真实搜索结果后，才能 Final Answer。
4. Action Input 必须是 JSON，web_search 参数名固定为 query。

格式示例:
Thought: 用户要查纳斯达克走势，先搜索
Action: web_search
Action Input: {{"query": "纳斯达克 今日 走势"}}
"""


class ReActAgent(BaseAgent):
    """ReAct 模式 Agent"""

    def __init__(
        self,
        name: str,
        role: str,
        llm: BaseChatModel,
        tools: list[BaseTool],
        system_prompt: str | None = None,
        max_tool_calls: int = 10,
    ):
        super().__init__(name, role, llm, tools, system_prompt or REACT_SYSTEM_PROMPT)
        self.max_tool_calls = max_tool_calls

    def _get_tools_description(self) -> str:
        if not self.tools:
            return "（没有可用的工具）"
        lines = []
        for tool in self.tools:
            lines.append(f"- {tool.name}: {tool.description}")
            schema_fn = getattr(tool.args_schema, "model_json_schema", None) or getattr(
                tool.args_schema, "schema", None
            )
            if tool.args_schema and schema_fn:
                try:
                    lines.append(f"  参数: {schema_fn()}")
                except Exception:
                    pass
        return "\n".join(lines)

    def _get_tool_by_name(self, name: str) -> BaseTool | None:
        cleaned = name.lower().strip().strip("`\"'")
        for tool in self.tools:
            if tool.name.lower() == cleaned:
                return tool
        return None

    def _has_web_search(self) -> bool:
        """工具列表里是否注册了 web_search。"""
        return self._get_tool_by_name("web_search") is not None

    def _needs_web_search(self, task: str) -> bool:
        """只有明显要联网查事实时才强制搜；闲聊/常识不搜。"""
        text = (task or "").lower()
        hints = (
            "新闻", "股价", "行情", "纳斯达克", "天气", "今日", "今天油价",
            "实时", "最新", "搜一下", "搜索", "查一下网上", "需要查询网页信息",
            "news", "stock", "weather", "price today",
        )
        return any(h in text for h in hints)

    def _parse_action(self, text: str) -> tuple[str | None, dict | None]:
        action_match = re.search(
            r"Action:\s*(.+?)(?:\n|$)", text, re.IGNORECASE
        )
        input_match = re.search(
            r"Action Input:\s*(\{.+?\}|.+?)(?:\n\s*(?:Observation|Thought|Action|Final)|$)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
        action = action_match.group(1).strip() if action_match else None
        if action:
            # 去掉模型可能加上的 markdown/句号
            action = action.strip().strip("`\"'").rstrip(".")
        action_input = None
        if input_match:
            raw = input_match.group(1).strip()
            try:
                action_input = json.loads(raw)
            except json.JSONDecodeError:
                action_input = {"input": raw}
        return action, action_input

    def _normalize_tool_input(
        self, tool: BaseTool, action_input: dict | None
    ) -> dict[str, Any]:
        """把常见错误入参映射成工具真正需要的字段（如 query）。"""
        data: dict[str, Any] = dict(action_input or {})
        if tool.name == "web_search":
            if "query" not in data:
                for k in ("input", "q", "search", "text", "keyword"):
                    if k in data and data[k]:
                        data = {"query": str(data[k])}
                        break
            if "query" not in data and len(data) == 1:
                data = {"query": str(next(iter(data.values())))}
        return data

    def _parse_final_answer(self, text: str) -> str | None:
        for pattern in [
            r"(?:Final\s*Answer|最终答案|答案)[：:]\s*(.+)",
            r"(?:Finish|Done|完成)[：:]\s*(.+)",
        ]:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    def _invoke_tool(self, tool: BaseTool, action_input: dict | None) -> str:
        """同步调用（web_search 等本地工具）。"""
        payload = self._normalize_tool_input(tool, action_input)
        try:
            result = tool.invoke(payload)
            return str(result)
        except Exception as e:
            # 单参数工具有时可用纯字符串
            if tool.name == "web_search" and "query" in payload:
                try:
                    return str(tool.invoke(payload["query"]))
                except Exception as e2:
                    return f"工具调用失败: {e2}"
            return f"工具调用失败: {e}"

    async def _ainvoke_tool(self, tool: BaseTool, action_input: dict | None) -> str:
        """异步调用；MCP / Playwright 工具必须走 ainvoke，否则会话会断。"""
        import asyncio

        payload = self._normalize_tool_input(tool, action_input)
        try:
            if hasattr(tool, "ainvoke"):
                result = await tool.ainvoke(payload)
            else:
                result = await asyncio.to_thread(tool.invoke, payload)
            return str(result)
        except Exception as e:
            if tool.name == "web_search" and "query" in payload:
                try:
                    return str(await asyncio.to_thread(tool.invoke, payload["query"]))
                except Exception as e2:
                    return f"工具调用失败: {e2}"
            return f"工具调用失败: {e}"

    async def think(self, task: str, context: Optional[dict] = None) -> tuple[str, object]:
        """返回 (模型文本, 原始 AIMessage)，方便外层抽 usage。

        context 约定（由 AgentUseCase 传入，本轮循环会追加字段）：
          - history: list[dict]，元素形如 {"role":"user"|"assistant","content":"..."}
          - format_reminder: 格式纠错提醒
          - last_tool_result: 上一轮 Observation
        """
        prompt = self.system_prompt.format(
            tools_description=self._get_tools_description()
        )
        messages: list = [SystemMessage(content=prompt)]

        # 注入多轮对话历史（与 chat 的 MessagesPlaceholder 同作用）
        if context and context.get("history"):
            messages.append(
                SystemMessage(
                    content=(
                        "以下是本会话最近对话历史，仅作上下文参考；"
                        "不要对历史消息再输出 Action，只服务当前「任务」。"
                    )
                )
            )
            for msg in context["history"]:
                role = (msg.get("role") or "").strip().lower()
                content = msg.get("content") or ""
                if not content:
                    continue
                if role == "user":
                    messages.append(HumanMessage(content=content))
                elif role in ("assistant", "ai"):
                    messages.append(AIMessage(content=content))

        # 格式纠错（解析失败时由 run() 写入）
        if context and context.get("format_reminder"):
            messages.append(HumanMessage(content=str(context["format_reminder"])))

        if context and "last_tool_result" in context:
            messages.append(
                HumanMessage(
                    content=(
                        "Observation:\n"
                        f"{context['last_tool_result']}\n\n"
                        "请基于以上 Observation 继续：若信息足够则输出 Final Answer: ..."
                        "；若还需工具则再输出 Action / Action Input。"
                    )
                )
            )

        messages.append(HumanMessage(content=f"任务: {task}\n请开始分析:"))
        response = await self.llm.ainvoke(messages)
        text = response.content or ""
        if not isinstance(text, str):
            text = str(text)
        return text, response

    def _force_web_search(self, task: str, context: Optional[dict]) -> dict:
        """模型拒不按 ReAct 格式调用时，直接执行一次 web_search，避免空跑。"""
        tool = self._get_tool_by_name("web_search")
        if not tool:
            return context or {}
        query = (task or "").strip()
        # 去掉过长前缀，保留检索核心
        if len(query) > 1000:
            query = query[:1000]
        _log.info("[%s] 强制调用 web_search query=%s", self.name, query[:80])
        obs = self._invoke_tool(tool, {"query": query})
        return (context or {}) | {"last_tool_result": obs, "forced_search": True}

    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        model_str = str(getattr(self.llm, "model_name", "") or "")
        usage_acc = empty_turn(model=model_str)  # 本 Agent 回合 token 累加器
        tool_calls_log: list[dict] = []
        tool_call_count = 0
        last_thought = ""
        consecutive_parse_failures = 0
        forced_once = False

        for iteration in range(self.max_tool_calls):
            thought, ai_msg = await self.think(task, context)
            usage_acc = merge_message(usage_acc, ai_msg, model=model_str)
            last_thought = thought
            _log.info("[%s] 第%s轮思考: %s...", self.name, iteration + 1, thought[:200])

            final_answer = self._parse_final_answer(thought)

            if final_answer:
                _log.info("[%s] 得到最终答案", self.name)
                return {
                    "agent": self.name,
                    "role": self.role,
                    "result": final_answer,
                    "tool_calls": tool_calls_log,
                    "iterations": iteration + 1,
                    "usage": usage_acc.to_dict(),
                }

            action_name, action_input = self._parse_action(thought)
            if not action_name:
                consecutive_parse_failures += 1
                #模型用自然语言直接答、没写Action->把整段当答案
                stripped = (thought or "").strip()
                if (
                    consecutive_parse_failures >= 1
                    and stripped 
                    and "action:" not in stripped.lower()
                ):
                    _log.info("[%s] 非ReAct格式，当作直接回答",self.name)
                    return {
                        "agent": self.name,
                        "role": self.role,
                        "result": stripped,
                        "tool_calls": tool_calls_log,
                        "iterations": iteration + 1,
                        "usage": usage_acc.to_dict(),
                    }
                

                # 仅[需要联网]的问题才强制搜一次
                if (
                    self._has_web_search()
                    and self._needs_web_search(task)
                    and not tool_calls_log
                    and not forced_once
                    and consecutive_parse_failures >= 1
                ):
                    context = self._force_web_search(task, context)
                    forced_once = True
                    tool_calls_log.append(
                        {
                            "iteration": iteration,
                            "tool": "web_search",
                            "input": {"query": task[:1000]},
                            "output": str(context.get("last_tool_result", ""))[:2000],
                            "forced": True,
                        }
                    )
                    tool_call_count += 1
                    consecutive_parse_failures = 0
                    context = (context or {}) | {
                        "format_reminder": (
                            "已为你执行 web_search，Observation 见上。"
                            "请输出 Final Answer: 基于搜索结果的中文总结（含关键数字/来源链接若有）。"
                        )
                    }
                    continue

                if consecutive_parse_failures >= 2:
                    _log.warning(
                        "[%s] LLM 连续%s次未按 ReAct 格式输出, 直接返回",
                        self.name,
                        consecutive_parse_failures,
                    )
                    # 若已有搜索结果，优先基于 Observation 返回，避免「无法联网」胡话
                    if context and context.get("last_tool_result"):
                        return {
                            "agent": self.name,
                            "role": self.role,
                            "result": (
                                "根据工具结果：\n"
                                f"{context['last_tool_result']}"
                            ),
                            "tool_calls": tool_calls_log,
                            "iterations": iteration + 1,
                            "usage": usage_acc.to_dict(),
                        }
                    return {
                        "agent": self.name,
                        "role": self.role,
                        "result": thought,
                        "tool_calls": tool_calls_log,
                        "iterations": iteration + 1,
                        "usage": usage_acc.to_dict(),
                    }

                context = (context or {}) | {
                    "format_reminder": (
                        "上一次输出不符合 ReAct 格式。请二选一：\n"
                        "A) 不需要工具 → 直接：\n"
                        "Thought: 不需要工具\n"
                        "Final Answer: 你的中文回答\n"
                        "B) 需要联网 →：\n"
                        "Thought: ...\n"
                        "Action: web_search\n"
                        'Action Input: {"query": "搜索词"}\n'
                    )
                }
                continue

            consecutive_parse_failures = 0

            tool = self._get_tool_by_name(action_name)
            if tool:
                obs = await self._ainvoke_tool(tool, action_input)
                tool_calls_log.append(
                    {
                        "iteration": iteration,
                        "tool": action_name,
                        "input": action_input,
                        "output": str(obs)[:800],
                    }
                )
                context = (context or {}) | {"last_tool_result": str(obs)}
                _log.info("[%s] 工具 %s 完成, obs_len=%s", self.name, action_name, len(str(obs)))
            else:
                context = (context or {}) | {
                    "last_tool_result": f"错误: 未找到工具 '{action_name}'，可用: "
                    f"{[t.name for t in self.tools]}"
                }

            tool_call_count += 1
            if tool_call_count >= self.max_tool_calls:
                break

        if context and context.get("last_tool_result") and not self._parse_final_answer(last_thought):
            return {
                "agent": self.name,
                "role": self.role,
                "result": f"根据工具结果：\n{context['last_tool_result']}",
                "tool_calls": tool_calls_log,
                "iterations": tool_call_count,
                "warning": "达到最大工具调用次数",
                "usage": usage_acc.to_dict(),
            }

        return {
            "agent": self.name,
            "role": self.role,
            "result": last_thought or "未完成",
            "tool_calls": tool_calls_log,
            "iterations": tool_call_count,
            "warning": "达到最大工具调用次数",
            "usage": usage_acc.to_dict(),
        }
