"""内嵌 Shell 执行 —— 对应 MyClaude promptShellExecution.ts

⚠️ 安全警告
===========
- 第 1～3 步完成前建议保持 ``enable_shell=False``
- MCP 来源技能禁止进入本模块（在 create_skill 里判断）
- 每条命令执行前必须走 ``permissions.has_permission_to_use_tool``
- 生产环境应用 Docker / 超时 / cwd 沙箱；教学版用 subprocess

支持语法
========
1. 内联：``!`echo hi` ``
2. 代码块::

       ```!
       ls -la
       ```
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess

from skills.types import FrontmatterShell, MalformedCommandError, ToolUseContext

BLOCK_PATTERN = re.compile(r"```!\s*\n([\s\S]*?)\n```")
INLINE_PATTERN = re.compile(r"!`([^`]+)`")


def is_powershell_enabled() -> bool:
    """判断是否允许使用 PowerShell。

    返回示例::

        # 在 Windows 上
        is_powershell_enabled()  # True

        # 在 Linux 且未设置环境变量
        is_powershell_enabled()  # False

        # 设置 CLAUDE_ENABLE_POWERSHELL=1 后
        is_powershell_enabled()  # True
    """
    return os.name == "nt" or os.environ.get("CLAUDE_ENABLE_POWERSHELL") == "1"


def format_shell_output(stdout: str, stderr: str) -> str:
    """合并 stdout / stderr 为可读文本。

    返回示例::

        format_shell_output("hello\\n", "")
        # "[stdout]\\nhello\\n"

        format_shell_output("", "boom")
        # "[stderr]\\nboom"

        format_shell_output("ok", "warn")
        # "[stdout]\\nok\\n[stderr]\\nwarn"
    """
    parts: list[str] = []
    if stdout:
        parts.append(f"[stdout]\n{stdout}")
    if stderr:
        parts.append(f"[stderr]\n{stderr}")
    return "\n".join(parts) if parts else "(no output)"


async def _run_command(command: str, shell: FrontmatterShell, cwd: str) -> str:
    """在指定 cwd 下执行一条命令（带 30s 超时）。

    返回示例::

        await _run_command("echo hi", "bash", ".")
        # "[stdout]\\nhi\\n"   （具体格式依赖系统 shell）

        await _run_command("Write-Output hi", "powershell", ".")
        # "[stdout]\\nhi\\n"
    """
    if shell == "powershell" and is_powershell_enabled():
        # 用 JSON 字符串字面量包一层，减少引号注入面（教学版仍非生产级）
        import json

        full = f"powershell -NoProfile -Command {json.dumps(command)}"
    else:
        full = command

    def _sync() -> str:
        try:
            p = subprocess.run(
                full,
                shell=True,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=30,
            )
            return format_shell_output(p.stdout or "", p.stderr or "")
        except subprocess.TimeoutExpired:
            return "[stderr]\ncommand timed out after 30s"
        except OSError as e:
            return f"[stderr]\n{e}"

    return await asyncio.to_thread(_sync)


async def execute_shell_commands_in_prompt(
    text: str,
    ctx: ToolUseContext,
    skill_name: str,
    shell: FrontmatterShell | None = None,
) -> str:
    """扫描文本中的内嵌 Shell，逐条权限检查后执行，用输出替换原文。

    返回示例::

        text = "版本：!`python --version`"
        await execute_shell_commands_in_prompt(text, ctx, "explain", "bash")
        # "版本：[stdout]\\nPython 3.12.x\\n"

        # 权限拒绝时抛出：
        # MalformedCommandError("skill 'explain' shell denied: blocked: ...")
    """
    chosen: FrontmatterShell = "bash"
    if shell == "powershell" and is_powershell_enabled():
        chosen = "powershell"

    result = text

    # ---- 1) 先处理代码块 ----
    # 在「当前 result」上反复 search，避免一边改一边用旧 match 下标
    while True:
        m = BLOCK_PATTERN.search(result)
        if not m:
            break
        cmd = m.group(1).strip()
        behavior, msg = await ctx.permissions.has_permission_to_use_tool(
            chosen, cmd, cwd=ctx.cwd, session_id=ctx.session_id
        )
        if behavior != "allow":
            raise MalformedCommandError(
                f"skill '{skill_name}' shell denied: {msg or cmd}"
            )
        output = await _run_command(cmd, chosen, ctx.cwd)
        result = result[: m.start()] + output + result[m.end() :]

    # ---- 2) 再处理内联 !`...` ----
    while True:
        m = INLINE_PATTERN.search(result)
        if not m:
            break
        cmd = m.group(1).strip()
        behavior, msg = await ctx.permissions.has_permission_to_use_tool(
            chosen, cmd, cwd=ctx.cwd, session_id=ctx.session_id
        )
        if behavior != "allow":
            raise MalformedCommandError(
                f"skill '{skill_name}' shell denied: {msg or cmd}"
            )
        output = await _run_command(cmd, chosen, ctx.cwd)
        result = result[: m.start()] + output + result[m.end() :]

    return result
