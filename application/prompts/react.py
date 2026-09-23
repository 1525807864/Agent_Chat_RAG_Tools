"""ReAct 系统提示拼装（去掉 AgentUseCase 内的重复字符串）。"""

from __future__ import annotations

_TOOLS_SLOT = "{tools_description}"

_FORMAT_BLOCK = (
    "请按以下格式响应:\n\n"
    "Thought: [...]\n"
    "Action: [工具名]\n"
    "Action Input: [JSON]\n"
    "Observation: [工具结果]\n"
    "...\n"
    "Final Answer: [最终答复]\n"
)

_FORMAT_SHORT = (
    "请按 Thought/Action/Action Input/Observation/Final Answer 格式响应。"
)


def coding_assistant_prompt(*, skill_extra: str = "") -> str:
    """带工作区规则的编程助手 system prompt。"""
    body = (
        f"你是编程助手，使用 ReAct 框架。可用工具:\n\n{_TOOLS_SLOT}\n\n"
        f"{_FORMAT_BLOCK}\n"
        "规则:\n"
        "1. 每次只调用一个工具；Action Input 必须是有效 JSON\n"
        "2. 工作区路径一律用相对路径（如 src/app.py），不要写绝对路径\n"
        "3. 用户要求修改/生成代码时，必须调用 write_workspace_file 写入磁盘，"
        "不要只在 Final Answer 里贴代码\n"
        "4. 写入前若不确定当前内容，先 read_workspace_file\n"
        "5. 可用 list_workspace_dir 浏览目录\n"
    )
    return body + (skill_extra or "")


def general_assistant_prompt(*, skill_extra: str = "") -> str:
    """通用 ReAct 助手 system prompt。"""
    body = (
        f"你是通用助手，使用 ReAct 框架。可用工具:\n\n{_TOOLS_SLOT}\n\n"
        f"{_FORMAT_SHORT}\n"
    )
    return body + (skill_extra or "")


def e2e_assistant_prompt(*, hint: str) -> str:
    """E2E / Playwright 专用 system prompt。"""
    return (
        f"你是 E2E 测试助手，使用 ReAct。可用工具:\n\n{_TOOLS_SLOT}\n\n"
        "格式: Thought / Action / Action Input / Observation / Final Answer\n"
        + (hint or "")
    )


def append_hint(system_prompt: str, hint: str) -> str:
    """追加发现提示等；已包含则不重复。"""
    if not hint:
        return system_prompt
    if hint in system_prompt:
        return system_prompt
    return system_prompt + hint
