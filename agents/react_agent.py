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

import json
import re
from typing import Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_core.messages import HumanMessage, SystemMessage

from agents.base_agent import BaseAgent


REACT_SYSTEM_PROMPT = """你是一个使用 ReAct 框架的智能助手。你可以使用以下工具:

{tools_description}

请按以下格式响应:

Thought: [分析当前情况, 决定下一步]
Action: [工具名称]
Action Input: [工具输入, JSON 格式]
Observation: [工具返回结果]
... (重复 Thought/Action/Action Input/Observation)

当得到最终答案时:
Thought: 我已收集到足够信息
Final Answer: [最终答案]

规则:
1. 每次只调用一个工具
2. Action Input 必须是有效的 JSON
3. 不要编造 Observation 中没有的信息
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
            if hasattr(tool, "args_schema") and tool.args_schema:
                lines.append(f"  参数: {tool.args_schema.schema()}")
        return "\n".join(lines)

    def _get_tool_by_name(self, name: str) -> BaseTool | None:
        for tool in self.tools:
            if tool.name.lower() == name.lower().strip():
                return tool
        return None

    def _parse_action(self, text: str) -> tuple[str | None, dict | None]:
        action_match = re.search(
            r'Action:\s*(.+?)(?:\n|$)', text, re.IGNORECASE
        )
        input_match = re.search(
            r'Action Input:\s*(\{.+?\}|.+?)(?:\n\s*(?:Observation|Thought|Action|Final)|$)',
            text, re.IGNORECASE | re.DOTALL,
        )
        action = action_match.group(1).strip() if action_match else None
        action_input = None
        if input_match:
            raw = input_match.group(1).strip()
            try:
                action_input = json.loads(raw)
            except json.JSONDecodeError:
                action_input = {"input": raw}
        return action, action_input

    def _parse_final_answer(self, text: str) -> str | None:
        for pattern in [
            r'(?:Final\s*Answer|最终答案|答案)[：:]\s*(.+)',
            r'(?:Finish|Done|完成)[：:]\s*(.+)',
        ]:
            match = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
        return None

    async def think(self, task: str, context: Optional[dict] = None) -> str:
        prompt = self.system_prompt.format(
            tools_description=self._get_tools_description()
        )
        messages = [SystemMessage(content=prompt)]

        if context and "last_tool_result" in context:
            messages.append(HumanMessage(
                content=f"Observation: {context['last_tool_result']}"
            ))

        messages.append(HumanMessage(content=f"任务: {task}\n请开始分析:"))
        response = await self.llm.ainvoke(messages)
        return response.content

    async def act(self, thought: str) -> str | None:
        final_answer = self._parse_final_answer(thought)
        if final_answer:
            return None

        action_name, action_input = self._parse_action(thought)
        if not action_name:
            return None

        tool = self._get_tool_by_name(action_name)
        if not tool:
            return f"错误: 未找到工具 '{action_name}'"

        try:
            result = tool.invoke(action_input or {})
            return str(result)
        except Exception as e:
            return f"工具调用失败: {str(e)}"

    async def run(self, task: str, context: Optional[dict] = None) -> dict:
        import logging
        _log = logging.getLogger(__name__)

        tool_calls_log = []
        tool_call_count = 0
        last_thought = ""
        consecutive_parse_failures = 0

        for iteration in range(self.max_tool_calls):
            thought = await self.think(task, context)
            last_thought = thought
            _log.info(f"[{self.name}] 第{iteration+1}轮思考: {thought[:200]}...")

            final_answer = self._parse_final_answer(thought)
            if final_answer:
                _log.info(f"[{self.name}] 得到最终答案")
                return {
                    "agent": self.name, "role": self.role,
                    "result": final_answer, "tool_calls": tool_calls_log,
                    "iterations": iteration + 1,
                }

            action_name, action_input = self._parse_action(thought)
            if not action_name:
                consecutive_parse_failures += 1
                if consecutive_parse_failures >= 2:
                    _log.warning(f"[{self.name}] LLM 连续{consecutive_parse_failures}次未按 ReAct 格式输出, 直接返回")
                    return {
                        "agent": self.name, "role": self.role,
                        "result": thought, "tool_calls": tool_calls_log,
                        "iterations": iteration + 1,
                    }
                continue

            consecutive_parse_failures = 0

            tool = self._get_tool_by_name(action_name)
            if tool:
                try:
                    obs = tool.invoke(action_input or {})
                    tool_calls_log.append({
                        "iteration": iteration, "tool": action_name,
                        "input": action_input, "output": str(obs),
                    })
                    context = (context or {}) | {"last_tool_result": str(obs)}
                except Exception as e:
                    context = (context or {}) | {"last_tool_result": f"工具错误: {e}"}

            tool_call_count += 1
            if tool_call_count >= self.max_tool_calls:
                break

        return {
            "agent": self.name, "role": self.role,
            "result": last_thought or "未完成",
            "tool_calls": tool_calls_log, "iterations": tool_call_count,
            "warning": "达到最大工具调用次数",
        }
