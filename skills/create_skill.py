"""把 SKILL.md 包装成 Command —— 对应 MyClaude createSkillCommand.ts

管线顺序（必须与 MyClaude 一致）::

    1. substitute_arguments   参数替换
    2. expand_builtin_variables 内置变量
    3. （可选）execute_shell_commands_in_prompt  内嵌 Shell
       —— MCP 来源永远跳过第 3 步，防止 RCE
"""

from __future__ import annotations

from skills.substitute import expand_builtin_variables, substitute_arguments
from skills.types import (
    Command,
    PromptContentBlock,
    SkillFrontmatterFields,
    SkillLoadedFrom,
    ToolUseContext,
)


def create_skill_command(
    *,
    skill_name: str,
    markdown_content: str,
    loaded_from: SkillLoadedFrom,
    fields: SkillFrontmatterFields,
    base_dir: str | None = None,
    enable_shell: bool = False,
) -> Command:
    """工厂：fields + 正文 → 可调用的 Command。

    参数:
        skill_name: 技能名，如 ``"explain"``
        markdown_content: SKILL.md 去掉 frontmatter 后的正文
        loaded_from: 来源信任等级
        fields: 解析后的 frontmatter 字段
        base_dir: 技能目录绝对路径
        enable_shell: 是否启用内嵌 Shell（第 4 步再开；默认 False）

    返回示例::

        cmd = create_skill_command(
            skill_name="explain",
            markdown_content="请解释 ${topic}",
            loaded_from=SkillLoadedFrom.PROJECT,
            fields=SkillFrontmatterFields(arguments=["topic"]),
            base_dir="D:/proj/data/skills/explain",
        )
        # Command(name="explain", loaded_from=PROJECT, is_hidden=False, ...)

        blocks = await cmd.get_prompt_for_command(["装饰器"], ctx)
        # [PromptContentBlock(type="text", text="请解释 装饰器")]
    """
    # user_invocable 默认 True；显式 False 才隐藏
    user_invocable = fields.user_invocable is not False

    desc = fields.description
    if isinstance(desc, list):
        description = "\n".join(desc)
    else:
        description = desc

    argument_names = fields.arguments
    shell = fields.shell

    async def get_prompt_for_command(
        args: list[str],
        ctx: ToolUseContext,
    ) -> list[PromptContentBlock]:
        """真正展开技能正文。

        返回示例::

            [PromptContentBlock(type="text", text="请解释 装饰器\\n会话：sess-001")]
        """
        # 1) 参数替换
        text = substitute_arguments(
            markdown_content,
            args,
            named=True,
            argument_names=argument_names,
        )
        # 2) 内置变量
        text = expand_builtin_variables(text, base_dir, ctx.session_id)

        # 3) 内嵌 Shell（默认关闭；MCP 来源永远禁止）
        if (
            enable_shell
            and loaded_from != SkillLoadedFrom.MCP
        ):
            from skills.shell_execution import execute_shell_commands_in_prompt

            text = await execute_shell_commands_in_prompt(
                text,
                ctx,
                skill_name,
                shell,
            )

        return [PromptContentBlock(type="text", text=text)]

    return Command(
        name=skill_name,
        loaded_from=loaded_from,
        get_prompt_for_command=get_prompt_for_command,
        description=description,
        paths=fields.paths,
        is_hidden=not user_invocable,
        allowed_tools=fields.allowed_tools,
        model=fields.model,
        effort=fields.effort,
        when_to_use=fields.when_to_use,
        context=fields.context,
        agent=fields.agent,
        version=fields.version,
        base_dir=base_dir,
    )
