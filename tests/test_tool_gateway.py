"""ToolGateway 冒烟：本地工具拼装与 discovery 关闭时的会话。"""

from __future__ import annotations

import pytest
from langchain_core.tools import tool

from application.tools.gateway import AssembledTools, ToolGateway


@tool
def _ping() -> str:
    """ping"""
    return "pong"


class _FakeRegistry:
    def get_all_tools(self):
        return [_ping]


@pytest.mark.asyncio
async def test_tool_gateway_open_act_session_no_mcp():
    gw = ToolGateway(
        _FakeRegistry(),
        mcp_servers_json="",
        active_tool_discovery=False,
    )
    async with gw.open_act_session() as assembled:
        assert isinstance(assembled, AssembledTools)
        assert len(assembled.tools) == 1
        assert assembled.tools[0].name == "_ping"
        assert assembled.discovery_hint == ""
        assert assembled.toolkit is None


def test_build_files_prefix():
    from application.prompts.files import build_files_prefix

    assert build_files_prefix(None) == ""
    out = build_files_prefix([{"path": "a.py", "content": "print(1)"}])
    assert "### FILE: a.py" in out
    assert "print(1)" in out


def test_react_prompts():
    from application.prompts.react import (
        append_hint,
        coding_assistant_prompt,
        general_assistant_prompt,
    )

    c = coding_assistant_prompt()
    assert "{tools_description}" in c
    assert "write_workspace_file" in c
    g = general_assistant_prompt(skill_extra="\n# skill")
    assert "# skill" in g
    assert append_hint("base", "HINT") == "baseHINT"
    assert append_hint("baseHINT", "HINT") == "baseHINT"
