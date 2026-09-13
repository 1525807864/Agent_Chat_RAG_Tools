"""参数与内置变量替换 —— 对应 MyClaude substitute.ts

支持三类替换：
1. ``$ARGUMENTS`` → 所有参数空格拼接
2. ``$1`` ``$2`` … → 位置参数（从 1 开始）
3. ``${file}`` → 命名参数（需传入 argument_names）
以及内置变量 ``${CLAUDE_SKILL_DIR}`` / ``${CLAUDE_SESSION_ID}``。
"""

from __future__ import annotations

import re


def _escape_regex(value: str) -> str:
    """把普通字符串转成正则安全字面量。

    返回示例::

        _escape_regex("file.name")  # "file\\.name"
        _escape_regex("a+b")        # "a\\+b"
    """
    return re.escape(value)


def substitute_arguments(
    content: str,
    args: list[str],
    *,
    named: bool = True,
    argument_names: list[str] | None = None,
) -> str:
    """展开 CLI 参数占位符。

    参数:
        content: 原始 markdown 正文
        args: 用户传入的参数列表，如 ``["foo.py", "strict"]``
        named: 是否启用 ``${name}`` 命名占位符
        argument_names: 命名占位符顺序，如 ``["file", "mode"]``

    返回示例::

        substitute_arguments(
            "看 $ARGUMENTS；文件=$1；${file}",
            ["foo.py", "strict"],
            named=True,
            argument_names=["file", "mode"],
        )
        # "看 foo.py strict；文件=foo.py；foo.py"

        substitute_arguments("只有 $2", ["a"])
        # "只有 "   （越界位置变成空串）
    """
    result = content

    # 1) 全部参数拼接（空格分开，避免 foo+bar 粘成 foobar）
    result = result.replace("$ARGUMENTS", " ".join(args))

    # 2) 位置参数：$1 → args[0]
    def repl_pos(m: re.Match[str]) -> str:
        idx = int(m.group(1)) - 1
        return args[idx] if 0 <= idx < len(args) else ""

    result = re.sub(r"\$(\d+)", repl_pos, result)

    # 3) 命名参数：${file} → args[i]（按 argument_names 顺序）
    if named and argument_names:
        for i, name in enumerate(argument_names):
            pattern = re.compile(r"\$\{" + _escape_regex(name) + r"\}")
            value = args[i] if i < len(args) else ""
            result = pattern.sub(value, result)

    return result


def expand_builtin_variables(
    content: str,
    base_dir: str | None,
    session_id: str,
) -> str:
    """展开内置变量 ``${CLAUDE_SKILL_DIR}`` / ``${CLAUDE_SESSION_ID}``。

    参数:
        content: 待处理文本
        base_dir: 技能所在目录（可 None；为 None 时不替换 SKILL_DIR）
        session_id: 当前会话 ID

    返回示例::

        expand_builtin_variables(
            "目录=${CLAUDE_SKILL_DIR} 会话=${CLAUDE_SESSION_ID}",
            base_dir=r"D:\\proj\\skills\\explain",
            session_id="sess-001",
        )
        # "目录=D:/proj/skills/explain 会话=sess-001"

        expand_builtin_variables(
            "会话=${CLAUDE_SESSION_ID}",
            base_dir=None,
            session_id="sess-002",
        )
        # "会话=sess-002"
    """
    result = content
    if base_dir:
        # 统一成正斜杠，避免 Windows 反斜杠在 prompt 里难看
        skill_dir = base_dir.replace("\\", "/")
        result = result.replace("${CLAUDE_SKILL_DIR}", skill_dir)
    result = result.replace("${CLAUDE_SESSION_ID}", session_id)
    return result
