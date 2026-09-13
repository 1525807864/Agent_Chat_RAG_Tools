"""从用户消息里识别 slash skill 并展开成注入文本。

用法::

    用户输入: /explain 装饰器
    → 找到 name=explain 的 Command
    → 调用 get_prompt_for_command(["装饰器"], ctx)
    → 得到要注入 LLM 的 PromptContentBlock 列表
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from skills.types import Command, PromptContentBlock, ToolUseContext

# 匹配：/explain foo.py bar  或  /code-review
_SLASH_RE = re.compile(
    r"^/([a-z0-9]+(?:-[a-z0-9]+)*)(?:\s+(.*))?$",
    re.DOTALL,
)


@dataclass
class ResolvedSkill:
    """slash 技能解析成功后的结果。

    字段示例::

        ResolvedSkill(
            command=Command(name="explain", ...),
            args=["装饰器"],
            blocks=[PromptContentBlock(type="text", text="请解释 装饰器")],
            remainder_user_text="装饰器",
        )
    """

    command: Command
    args: list[str]
    blocks: list[PromptContentBlock]
    # 去掉 /skill 后剩余文本；也可整段替换成技能正文
    remainder_user_text: str


async def try_resolve_skill(
    user_text: str,
    commands: list[Command],
    ctx: ToolUseContext,
) -> ResolvedSkill | None:
    """若 user_text 以 ``/skill-name`` 开头，则展开对应技能；否则返回 None。

    返回示例::

        # 命中技能
        await try_resolve_skill("/explain 装饰器", [explain_cmd], ctx)
        # ResolvedSkill(
        #   command=explain_cmd,
        #   args=["装饰器"],
        #   blocks=[PromptContentBlock(..., text="请解释 装饰器")],
        #   remainder_user_text="装饰器",
        # )

        # 普通聊天（无 slash）
        await try_resolve_skill("你好", [explain_cmd], ctx)
        # None

        # slash 了但不存在的技能
        await try_resolve_skill("/nope", [explain_cmd], ctx)
        # None

        # 条件技能 paths 不匹配 → 显式 /skill 仍会命中（paths 仅用于自动激活）
        # await try_resolve_skill("/explain x", [explain_cmd], ctx_with_md_file)
        # ResolvedSkill(...)  # 仍然成功
    """
    text = user_text.strip()
    m = _SLASH_RE.match(text)
    if not m:
        return None

    name = m.group(1)
    rest = (m.group(2) or "").strip()
    args = rest.split() if rest else []

    # 隐藏技能（user_invocable=false）不出现在用户 slash 列表
    by_name = {c.name: c for c in commands if not c.is_hidden}
    cmd = by_name.get(name)
    if cmd is None:
        return None

    # 注意：用户显式输入 /skill 时不再用 paths 拦截。
    # paths 只用于「自动激活 / 推荐」场景（skills.path_match.is_skill_active_for_path）。
    # 否则 /explain 装饰器 在没打开 .py 文件时会被误判为未命中。

    blocks = await cmd.get_prompt_for_command(args, ctx)
    return ResolvedSkill(
        command=cmd,
        args=args,
        blocks=blocks,
        remainder_user_text=rest,
    )
