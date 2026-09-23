"""ask_agent 用的一站式入口：开 MCP +（可选）主动发现。"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from langchain_core.tools import BaseTool

from application.mcp.active import ActiveToolKit
from application.mcp.loader import parse_mcp_servers_json
from application.mcp.session import open_mcp_tools


@asynccontextmanager
async def open_mcp_bundle(
    servers_json: str,
) -> AsyncIterator[list[BaseTool]]:
    """解析配置并打开 MCP；没有配置则 yield 空列表。"""
    specs = parse_mcp_servers_json(servers_json)
    async with open_mcp_tools(specs) as tools:
        yield tools


def build_active_toolkit(
    pool: list[BaseTool],
    *,
    enabled: bool,
    base_names: list[str],
    top_k: int,
) -> ActiveToolKit | None:
    """关闭主动发现时返回 None，调用方用全量 pool。"""
    if not enabled:
        return None
    return ActiveToolKit(pool, base_names=base_names, top_k=top_k)


ACTIVE_DISCOVERY_HINT = """
【工具发现】
你一开始只有少量基础工具和 discover_tools。
若当前工具不够完成任务：先 Action: discover_tools，
Action Input: {"need": "你缺什么能力的中文描述"}。
解锁成功后，再 Action 具体业务工具。不要编造未解锁的工具名。
"""
