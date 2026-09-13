# skills 核心类型
"""
设计要点
========
1. Skill 不是「工具」，而是「提示词工厂」：最终产出要注入给 LLM 的文本。
2. loaded_from 决定信任等级：mcp 最低，policy 最高。
3. 本文件只放数据结构，不要写 IO / 业务逻辑。
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Awaitable, Callable, Literal, Optional, Protocol

# ---------------------------------------------------------------------------
# 枚举 / 字面量类型
# ---------------------------------------------------------------------------


class EffortValue(str, Enum):
    """任务估时档位：可映射到 temperature / max_tokens。

    返回/取值示例::

        EffortValue.LOW      # == "low"
        EffortValue.MEDIUM   # == "medium"
        EffortValue("high")  # EffortValue.HIGH
    """

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SkillContextMode(str, Enum):
    """技能上下文模式。

    - inline: 技能正文注入当前会话（默认）
    - fork  : 开独立子会话，避免污染主会话历史

    返回/取值示例::

        SkillContextMode.INLINE  # "inline"
        SkillContextMode.FORK    # "fork"
    """

    INLINE = "inline"
    FORK = "fork"


class SkillLoadedFrom(str, Enum):
    """技能来源（信任从低到高）。

    mcp < user < project < policy

    同名技能冲突时，高信任覆盖低信任（见 load_skills.SOURCE_RANK）。

    返回/取值示例::

        SkillLoadedFrom.MCP      # "mcp"
        SkillLoadedFrom.USER     # "userSettings"
        SkillLoadedFrom.PROJECT  # "projectSettings"
        SkillLoadedFrom.POLICY   # "policySettings"
    """

    MCP = "mcp"
    USER = "userSettings"
    PROJECT = "projectSettings"
    POLICY = "policySettings"


# frontmatter.shell 字段的合法取值
FrontmatterShell = Literal["bash", "powershell"]


# ---------------------------------------------------------------------------
# Frontmatter 解析结果
# ---------------------------------------------------------------------------


@dataclass
class SkillFrontmatterFields:
    """SKILL.md 开头 ``--- YAML ---`` 解析后的结构化字段。

    返回/构造示例::

        SkillFrontmatterFields(
            name="explain",
            description="解释代码",
            arguments=["topic"],
            paths=["**/*.py"],
            context=SkillContextMode.INLINE,
        )
    """

    name: Optional[str] = None
    description: Optional[str | list[str]] = None
    when_to_use: Optional[str] = None
    # 允许使用的工具白名单；第 3 步接到 ToolRegistry
    allowed_tools: Optional[list[str]] = None
    model: Optional[str] = None
    effort: Optional[EffortValue] = None
    # False = 仅模型内部可用，不出现在用户 / 命令列表
    user_invocable: Optional[bool] = None
    # 条件技能：匹配当前打开文件的 glob 才激活
    paths: Optional[list[str]] = None
    version: Optional[str] = None
    context: Optional[SkillContextMode] = None
    # 绑定到 multi-agent 里的某个 agent 名，如 "coder"
    agent: Optional[str] = None
    shell: Optional[FrontmatterShell] = None
    # 命名参数顺序：["file", "mode"] 对应 ${file} ${mode}
    arguments: Optional[list[str]] = None


# ---------------------------------------------------------------------------
# 权限
# ---------------------------------------------------------------------------


class PermissionChecker(Protocol):
    """工具执行前的权限检查接口（先定义，后在 permissions.py 实现）。"""

    async def has_permission_to_use_tool(
        self,
        tool_name: str,
        command: str,
        *,
        cwd: str,
        session_id: str,
    ) -> tuple[Literal["allow", "deny"], Optional[str]]:
        """检查是否允许执行某工具。

        返回示例::

            ("allow", None)
            ("deny", "blocked: bash :: rm -rf /")
        """
        ...


@dataclass
class ToolUseContext:
    """一次技能展开时的运行时上下文。

    返回/构造示例::

        ToolUseContext(
            cwd="D:/LangChain_Demo",
            session_id="sess-001",
            permissions=allow_all_permissions(),
            active_file="src/app.py",
        )
    """

    cwd: str
    session_id: str
    permissions: PermissionChecker
    # 可选：当前打开的文件（条件技能用）
    active_file: Optional[str] = None
    logger: Optional[Callable[[str], None]] = None


@dataclass
class PromptContentBlock:
    """注入给模型的内容块（教学版只支持 text）。

    返回/构造示例::

        PromptContentBlock(type="text", text="请解释装饰器...")
    """

    type: Literal["text"] = "text"
    text: str = ""


# get_prompt 的异步函数签名
GetPromptFn = Callable[
    [list[str], ToolUseContext],
    Awaitable[list[PromptContentBlock]],
]


@dataclass
class Command:
    """统一的「技能命令」对象。

    关键方法是 ``get_prompt_for_command``：
    用户输入 ``/explain foo.py`` 时，宿主调用它，得到要注入 LLM 的文本。

    返回/构造示例::

        Command(
            name="explain",
            loaded_from=SkillLoadedFrom.PROJECT,
            get_prompt_for_command=some_async_fn,
            description="解释代码",
            base_dir="D:/LangChain_Demo/data/skills/explain",
        )
    """

    name: str
    loaded_from: SkillLoadedFrom
    get_prompt_for_command: GetPromptFn
    type: Literal["prompt"] = "prompt"
    description: Optional[str] = None
    paths: Optional[list[str]] = None
    is_hidden: bool = False
    allowed_tools: Optional[list[str]] = None
    model: Optional[str] = None
    effort: Optional[EffortValue] = None
    when_to_use: Optional[str] = None
    context: Optional[SkillContextMode] = None
    agent: Optional[str] = None
    version: Optional[str] = None
    # 技能所在目录，用于 ${CLAUDE_SKILL_DIR} 与 realpath 去重
    base_dir: Optional[str] = None


class MalformedCommandError(Exception):
    """权限拒绝、语法错误等——宿主应捕获并返回给用户，不要当未处理异常。

    抛出示例::

        raise MalformedCommandError("skill 'explain' shell denied: blocked: rm -rf /")
    """
