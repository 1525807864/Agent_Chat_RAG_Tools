"""工具网关：注册表本地工具 + MCP +（可选）主动发现。

Agent 只拿「当前可见工具」，不关心 npx / MultiServerMCPClient 细节。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional

from langchain_core.tools import BaseTool

from agents.tools_registry import make_workspace_tools
from application.mcp.active import ActiveToolKit
from application.mcp.bundle import (
    ACTIVE_DISCOVERY_HINT,
    build_active_toolkit,
    open_mcp_bundle,
)


@dataclass
class AssembledTools:
    """一轮 Act 会话可用的工具集合。"""

    tools: list[BaseTool]
    discovery_hint: str = ""
    toolkit: Optional[ActiveToolKit] = None

    def bind_agent(self, agent: Any) -> None:
        """若启用主动发现，把 agent 挂到 toolkit 以便 unlock 时追加工具。"""
        if self.toolkit is not None:
            self.toolkit.bind_agent(agent)


class ToolGateway:
    """统一拼装本地工具与 MCP；E2E Playwright 仍走专用通路。"""

    def __init__(
        self,
        registry: Any,
        *,
        mcp_servers_json: str = "",
        active_tool_discovery: bool = False,
        active_tool_base: str = "",
        active_tool_top_k: int = 8,
        logger: Any = None,
    ) -> None:
        self._registry = registry
        self._mcp_servers_json = mcp_servers_json or ""
        self._active_discovery = bool(active_tool_discovery)
        self._active_base = active_tool_base or ""
        self._active_top_k = int(active_tool_top_k)
        self._logger = logger

    def local_tools(self, *, workspace_root: str | None = None) -> list[BaseTool]:
        """注册表工具 +（可选）工作区读写工具。"""
        tools = list(self._registry.get_all_tools())
        if not workspace_root:
            return tools
        try:
            return tools + make_workspace_tools(workspace_root)
        except Exception as e:  # noqa: BLE001
            if self._logger is not None:
                self._logger.warning("注入工作区工具失败: %s", e)
            return tools

    @asynccontextmanager
    async def open_act_session(
        self,
        *,
        workspace_root: str | None = None,
    ) -> AsyncIterator[AssembledTools]:
        """打开 MCP，拼出本轮工具池（含主动发现初值）。"""
        local = self.local_tools(workspace_root=workspace_root)
        base_names = [
            x.strip() for x in self._active_base.split(",") if x.strip()
        ]
        async with open_mcp_bundle(self._mcp_servers_json) as mcp_tools:
            pool = list(local) + list(mcp_tools)
            toolkit = build_active_toolkit(
                pool,
                enabled=self._active_discovery,
                base_names=base_names,
                top_k=self._active_top_k,
            )
            if toolkit is not None:
                yield AssembledTools(
                    tools=toolkit.initial_tools(),
                    discovery_hint=ACTIVE_DISCOVERY_HINT,
                    toolkit=toolkit,
                )
            else:
                yield AssembledTools(tools=pool, discovery_hint="", toolkit=None)
