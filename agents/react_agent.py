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

import json
import logging
import re
from typing import Any, Optional

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import BaseTool

from agents.base_agent import BaseAgent

_log = logging.getLogger(__name__)

REACT_SYSTEM_PROMPT = """你是一个使用 ReAct 框架的智能助手。你可以使用以下工具:

{tools_description}

请严格按以下格式响应（不要省略 Action/Action Input 行）:

Thought: [分析当前情况, 决定下一步]
Action: [工具名称]
Action Input: [工具输入, 必须是 JSON 对象]

系统会返回 Observation。你可以重复 Thought/Action/Action Input。

当已有足够 Observation 时:
Thought: 我已收集到足够信息
Final Answer: [最终答案]

规则:
1. 每次只调用一个工具
2. Action Input 必须是有效 JSON（例如 {{"query": "关键词"}}）
3. 不要编造 Observation 中没有的信息
4. 若工具列表含 web_search：查询新闻/股价/行情/实时事实时必须先 Action: web_search，禁止声称无法联网或让用户自己去查网页
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
        return any(t.name == "web_search" for t in self.tools)

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

    async def think(self, task: str, context: Optional[dict] = None) -> str:
        prompt = self.system_prompt.format(
            tools_description=self._get_tools_description()
        )
        messages = [SystemMessage(content=prompt)]

        if context and context.get("format_reminder"):
            messages.append(HumanMessage(content=str(context["format_reminder"])))

        if context and "last_tool_result" in context:
            messages.append(
                HumanMessage(
                    content=(
                        "Observation:\n"
                        f"{context['last_tool_result']}\n\n"
                        "请基于以上 Observation 继续：若信息足够则输出 Final Answer: ..."
                        "；若还需搜索则再次 Action: web_search。"
                    )
                )
            )

        messages.append(HumanMessage(content=f"任务: {task}\n请开始分析:"))
        response = await self.llm.ainvoke(messages)
        return response.content or ""

    def _force_web_search(self, task: str, context: Optional[dict]) -> dict:
        """模型拒不按 ReAct 格式调用时，直接执行一次 web_search，避免空跑。"""
        tool = self._get_tool_by_name("web_search")
        if not tool:
            return context or {}
        query = (task or "").strip()
        # 去掉过长前缀，保留检索核心
        if len(query) > 200:
            query = query[:200]
        _log.info("[%s] 强制调用 web_search query=%s", self.name, query[:80])
        obs = self._invoke_tool(tool, {"query": query})
        return (context or {}) | {"last_tool_result": obs, "forced_search": True}

    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        tool_calls_log: list[dict] = []
        tool_call_count = 0
        last_thought = ""
        consecutive_parse_failures = 0
        forced_once = False

        for iteration in range(self.max_tool_calls):
            thought = await self.think(task, context)
            last_thought = thought
            _log.info("[%s] 第%s轮思考: %s...", self.name, iteration + 1, thought[:200])

            final_answer = self._parse_final_answer(thought)
            # 若还没搜过就宣称 Final Answer / 无法联网 → 先强制搜索
            if final_answer and self._has_web_search() and not tool_calls_log and not forced_once:
                context = self._force_web_search(task, context)
                forced_once = True
                tool_calls_log.append(
                    {
                        "iteration": iteration,
                        "tool": "web_search",
                        "input": {"query": task[:200]},
                        "output": str(context.get("last_tool_result", ""))[:500],
                        "forced": True,
                    }
                )
                tool_call_count += 1
                continue

            if final_answer:
                _log.info("[%s] 得到最终答案", self.name)
                return {
                    "agent": self.name,
                    "role": self.role,
                    "result": final_answer,
                    "tool_calls": tool_calls_log,
                    "iterations": iteration + 1,
                }

            action_name, action_input = self._parse_action(thought)
            if not action_name:
                consecutive_parse_failures += 1
                # 有 web_search 且尚未调用：第一次失败就强制搜，避免连续空转
                if (
                    self._has_web_search()
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
                            "input": {"query": task[:200]},
                            "output": str(context.get("last_tool_result", ""))[:500],
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
                                "根据 web_search 结果：\n"
                                f"{context['last_tool_result']}"
                            ),
                            "tool_calls": tool_calls_log,
                            "iterations": iteration + 1,
                        }
                    return {
                        "agent": self.name,
                        "role": self.role,
                        "result": thought,
                        "tool_calls": tool_calls_log,
                        "iterations": iteration + 1,
                    }

                context = (context or {}) | {
                    "format_reminder": (
                        "上一次输出不符合 ReAct 格式。请立刻输出：\n"
                        "Thought: ...\n"
                        "Action: web_search\n"
                        'Action Input: {"query": "与任务相关的搜索词"}\n'
                        "不要说无法联网。"
                    )
                }
                continue

            consecutive_parse_failures = 0

            tool = self._get_tool_by_name(action_name)
            if tool:
                obs = self._invoke_tool(tool, action_input)
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
            }

        return {
            "agent": self.name,
            "role": self.role,
            "result": last_thought or "未完成",
            "tool_calls": tool_calls_log,
            "iterations": tool_call_count,
            "warning": "达到最大工具调用次数",
        }
