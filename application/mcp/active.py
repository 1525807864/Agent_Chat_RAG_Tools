"""主动工具发现：Agent 初始只有 base + discover_tools，按需把工具追加进 agent.tools。

依赖 ReActAgent.think() 每轮重新 _get_tools_description()。
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from application.mcp.catalog import ToolCatalog

_log = logging.getLogger(__name__)


class DiscoverInput(BaseModel):
    """discover_tools 的入参 schema，给模型看。"""

    need: str = Field(
        description="用自然语言描述你缺什么能力，例如：查天气、读 PDF、操作浏览器点击"
    )


class ActiveToolKit:
    """把「全量池」收成「初始工具 + 发现元工具」。"""

    def __init__(
        self,
        pool: list[BaseTool],
        *,
        base_names: list[str],
        top_k: int = 5,
    ) -> None:
        self.catalog = ToolCatalog(pool)
        self.top_k = top_k
        self.base_names = [n.strip() for n in base_names if n.strip()]
        self._agent: Any = None
        self._unlocked: set[str] = set()

    def bind_agent(self, agent: Any) -> None:
        """必须在创建 ReActAgent 后立刻调用。"""
        self._agent = agent

    def initial_tools(self) -> list[BaseTool]:
        """Agent 构造时用的工具列表：base ∩ 池子 + discover_tools。"""
        tools: list[BaseTool] = []
        for name in self.base_names:
            if name == "discover_tools":
                continue
            t = self.catalog.get(name)
            if t is not None:
                tools.append(t)
                self._unlocked.add(t.name)
        tools.append(self._make_discover_tool())
        self._unlocked.add("discover_tools")
        return tools

    def _make_discover_tool(self) -> BaseTool:
        async def _arun(need: str) -> str:
            return self._discover(need)

        def _run(need: str) -> str:
            return self._discover(need)

        return StructuredTool.from_function(
            name="discover_tools",
            description=(
                "当你缺少完成任务的能力时调用。传入自然语言需求，"
                "系统会检索并解锁最相关的工具；解锁后下一轮即可 Action 那些工具。"
                "不要用它代替真正的业务工具。"
            ),
            args_schema=DiscoverInput,
            coroutine=_arun,
            func=_run,
        )

    def _discover(self, need: str) -> str:
        hits = self.catalog.search(need, top_k=self.top_k)
        if not hits:
            return f"没有找到与「{need}」匹配的工具。请换个说法，或使用已有工具。"

        added: list[str] = []
        for hit in hits:
            name = hit.tool.name
            if name in self._unlocked:
                continue
            if self._agent is not None:
                self._agent.tools.append(hit.tool)
            self._unlocked.add(name)
            added.append(f"{name} (score={hit.score:.2f}, {hit.reason})")

        if not added:
            names = [h.tool.name for h in hits]
            return f"相关工具早已解锁: {names}。请直接 Action 其中一个。"

        lines = ["已解锁以下工具，下一轮请直接 Action:"]
        for hit in hits:
            lines.append(f"- {hit.tool.name}: {hit.tool.description}")
        lines.append("已解锁: " + ", ".join(added))
        _log.info("discover_tools need=%s unlocked=%s", need[:80], added)
        return "\n".join(lines)
