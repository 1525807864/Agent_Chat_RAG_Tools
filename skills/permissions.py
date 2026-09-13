"""权限检查器 —— 对应 MyClaude permissions.ts

第 2 步目标：
1. allow_all / deny_all（单测与开发用）
2. PatternPermissionChecker（对接 settings.allowed_tool_patterns）
3. create_tool_use_context 工厂
"""

from __future__ import annotations

import fnmatch
from typing import Literal, Optional

from skills.types import PermissionChecker, ToolUseContext


def allow_all_permissions() -> PermissionChecker:
    """返回「全部放行」的权限检查器（仅本机测试 / 受信任环境）。

    返回示例::

        checker = allow_all_permissions()
        await checker.has_permission_to_use_tool(
            "bash", "echo hi", cwd=".", session_id="s1"
        )
        # ("allow", None)
    """

    class _Allow:
        async def has_permission_to_use_tool(
            self,
            tool_name: str,
            command: str,
            *,
            cwd: str,
            session_id: str,
        ) -> tuple[Literal["allow", "deny"], Optional[str]]:
            return ("allow", None)

    return _Allow()


def deny_all_permissions() -> PermissionChecker:
    """返回「全部拒绝」的权限检查器（用于验证拒绝路径）。

    返回示例::

        checker = deny_all_permissions()
        await checker.has_permission_to_use_tool(
            "bash", "rm -rf /", cwd=".", session_id="s1"
        )
        # ("deny", "blocked: bash :: rm -rf /")
    """

    class _Deny:
        async def has_permission_to_use_tool(
            self,
            tool_name: str,
            command: str,
            *,
            cwd: str,
            session_id: str,
        ) -> tuple[Literal["allow", "deny"], Optional[str]]:
            return ("deny", f"blocked: {tool_name} :: {command}")

    return _Deny()


class PatternPermissionChecker:
    """按 glob 白名单放行工具名。

    例：``allowed_patterns=["read_*", "calculator"]``
    → ``write_workspace_file`` 会被 deny。

    返回/用法示例::

        checker = PatternPermissionChecker(["read_*", "calculator"])
        await checker.has_permission_to_use_tool(
            "read_file", "data/a.txt", cwd=".", session_id="s1"
        )
        # ("allow", None)

        await checker.has_permission_to_use_tool(
            "write_workspace_file", "a.txt", cwd=".", session_id="s1"
        )
        # ("deny", "tool 'write_workspace_file' not in allowed_tool_patterns")
    """

    def __init__(self, allowed_patterns: list[str]) -> None:
        self.allowed_patterns = allowed_patterns or ["*"]

    async def has_permission_to_use_tool(
        self,
        tool_name: str,
        command: str,
        *,
        cwd: str,
        session_id: str,
    ) -> tuple[Literal["allow", "deny"], Optional[str]]:
        """按白名单检查工具名。

        返回示例::

            ("allow", None)
            ("deny", "tool 'bash' not in allowed_tool_patterns")
        """
        for pat in self.allowed_patterns:
            if fnmatch.fnmatch(tool_name, pat):
                return ("allow", None)
        return ("deny", f"tool '{tool_name}' not in allowed_tool_patterns")


def create_tool_use_context(
    *,
    cwd: str,
    session_id: str,
    permissions: PermissionChecker | None = None,
    active_file: str | None = None,
    logger=None,
) -> ToolUseContext:
    """组装一次技能展开所需的 ToolUseContext。

    返回示例::

        create_tool_use_context(
            cwd="D:/LangChain_Demo",
            session_id="sess-001",
            active_file="src/app.py",
        )
        # ToolUseContext(
        #   cwd="D:/LangChain_Demo",
        #   session_id="sess-001",
        #   permissions=<_Allow ...>,   # 默认 allow_all
        #   active_file="src/app.py",
        # )
    """
    return ToolUseContext(
        cwd=cwd,
        session_id=session_id,
        permissions=permissions or allow_all_permissions(),
        active_file=active_file,
        logger=logger,
    )
