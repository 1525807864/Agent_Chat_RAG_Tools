"""P2 多 Agent 结构评测（不强制真实 LLM）。"""

from __future__ import annotations

from agents.tools_registry import create_default_registry
from config.settings import get_settings
from shared.path_security import get_project_root


def test_execute_python_disabled_by_default():
    settings = get_settings()
    reg = create_default_registry(
        allowed_roots=settings.allowed_data_roots,
        project_root=get_project_root(),
        enable_execute_python=False,
    )
    assert reg.get_tool("execute_python") is None
    assert reg.get_tool("web_search") is not None


def test_execute_python_can_enable():
    settings = get_settings()
    reg = create_default_registry(
        allowed_roots=settings.allowed_data_roots,
        project_root=get_project_root(),
        enable_execute_python=True,
    )
    assert reg.get_tool("execute_python") is not None
