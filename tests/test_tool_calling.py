from __future__ import annotations

import pytest

from application.tools.gateway import ToolGateway
from agents.tools_registry import create_default_registry

# 默认注册表按注册顺序注册这三个工具（tools_registry.py:338-340）
EXPECTED_TOOL_NAMES = ["calculator", "web_search", "read_file"]


@pytest.mark.asyncio
async def test_tool_calling():
    gateway = ToolGateway(
        registry=create_default_registry(),
        mcp_servers_json="",
        active_tool_discovery=False,
        active_tool_base="",
        active_tool_top_k=8,
        logger=None,
    )
    async with gateway.open_act_session() as assembled:
        # 按工具名比较，避免工厂函数每次生成新实例导致身份比较失败
        assert [t.name for t in assembled.tools] == EXPECTED_TOOL_NAMES
        assert assembled.discovery_hint == ""
        assert assembled.toolkit is None
        assert len(assembled.tools) == len(EXPECTED_TOOL_NAMES)
