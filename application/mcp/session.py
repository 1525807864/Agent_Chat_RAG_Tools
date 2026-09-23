"""打开一个或多个 MCP 服务器，在 async with 期间交出 LangChain 工具列表。

对齐 e2e/mcp_playwright.py：
- 必须用 client.session(name) 保持有状态
- 用 load_mcp_tools(session) 转成 BaseTool
- 多个服务器时用 AsyncExitStack 嵌套 session；重名则加前缀
"""

from __future__ import annotations

import logging
from contextlib import AsyncExitStack, asynccontextmanager
from typing import AsyncIterator

from langchain_core.tools import BaseTool

from application.mcp.spec import McpServerSpec

_log = logging.getLogger(__name__)


def _unique_name(name: str, used: set[str], prefix: str) -> str:
    """避免两个 MCP 服务器工具同名互相覆盖。"""
    if name not in used:
        used.add(name)
        return name
    alt = f"{prefix}_{name}"
    n = 2
    while alt in used:
        alt = f"{prefix}_{name}_{n}"
        n += 1
    used.add(alt)
    return alt


@asynccontextmanager
async def open_mcp_tools(
    specs: list[McpServerSpec],
) -> AsyncIterator[list[BaseTool]]:
    """根据配置拉起 MCP，yield 全部工具；退出 with 时关掉所有 session。"""
    if not specs:
        yield []
        return

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
        from langchain_mcp_adapters.tools import load_mcp_tools
    except ImportError as exc:
        raise RuntimeError(
            "未安装 langchain-mcp-adapters，请 pip install langchain-mcp-adapters"
        ) from exc

    # 外层 key = 逻辑名；value = 连接配置（不要把 name 塞进 value）
    connections = {s.name: s.to_client_dict() for s in specs}
    client = MultiServerMCPClient(connections)
    _log.info("启动 MCP 服务器: %s", list(connections.keys()))

    async with AsyncExitStack() as stack:
        all_tools: list[BaseTool] = []
        used_names: set[str] = set()
        for spec in specs:
            session = await stack.enter_async_context(client.session(spec.name))
            tools = await load_mcp_tools(session)
            for tool in tools:
                new_name = _unique_name(tool.name, used_names, spec.name)
                if new_name != tool.name:
                    _log.warning("工具重名，重命名 %s -> %s", tool.name, new_name)
                    object.__setattr__(tool, "name", new_name)
                all_tools.append(tool)
            _log.info("MCP[%s] 工具数=%s", spec.name, len(tools))
        yield all_tools
