"""Skills 挂载钩子 — 被 ``AgentApplication`` 调用的纯函数工具。

业务入口
========
- ``AgentApplication._ensure_skills`` / ``_resolve_skill_for_turn``
- ``ask_chat`` / ``ask_agent`` 在推理前展开 ``/skill-name``
- HTTP：``api/routes/chat.py`` 把 ``files[0].path`` 作为 ``active_file`` 传入

本文件提供：``build_runtime_plan``、``resolve_and_build_skill_prefix``、
``effort_to_temperature``、``SkillRuntimePlan``。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from skills.permissions import allow_all_permissions, create_tool_use_context
from skills.resolve import ResolvedSkill, try_resolve_skill
from skills.types import Command, EffortValue, SkillContextMode


@dataclass
class SkillRuntimePlan:
    """根据 Command 元数据算出的「本轮怎么跑」。

    返回/构造示例::

        SkillRuntimePlan(
            session_id="skill-explain-a1b2c3d4",
            tool_names=["read_file"],
            agent_name="coder",
            model_name="deepseek-chat",
            temperature=0.2,
        )
    """

    session_id: str
    tool_names: list[str] | None
    agent_name: str | None
    model_name: str | None
    temperature: float | None


def effort_to_temperature(
    effort: EffortValue | None,
    default: float = 0.7,
) -> float:
    """把 effort 档位映射成 temperature。

    返回示例::

        effort_to_temperature(EffortValue.LOW)     # 0.2
        effort_to_temperature(EffortValue.MEDIUM)  # 0.5
        effort_to_temperature(EffortValue.HIGH)    # 0.8
        effort_to_temperature(None)                # 0.7
        effort_to_temperature(None, default=0.3)   # 0.3
    """
    if effort is None:
        return default
    return {
        EffortValue.LOW: 0.2,
        EffortValue.MEDIUM: 0.5,
        EffortValue.HIGH: 0.8,
    }[effort]


def build_runtime_plan(
    command: Command,
    *,
    base_session_id: str,
    default_tools: list[str] | None = None,
) -> SkillRuntimePlan:
    """由技能元数据生成运行时计划（fork / tools / model / agent）。

    返回示例::

        # command.context == FORK, allowed_tools=["read_file"], model="deepseek-chat"
        build_runtime_plan(command, base_session_id="sess-main")
        # SkillRuntimePlan(
        #   session_id="skill-explain-deadbeef",  # 新子会话
        #   tool_names=["read_file"],
        #   agent_name=None,
        #   model_name="deepseek-chat",
        #   temperature=0.7,
        # )

        # command.context == INLINE（或不设）
        build_runtime_plan(command, base_session_id="sess-main")
        # SkillRuntimePlan(session_id="sess-main", ...)
    """
    if command.context == SkillContextMode.FORK:
        session_id = f"skill-{command.name}-{uuid.uuid4().hex[:8]}"
    else:
        session_id = base_session_id

    tools = command.allowed_tools
    if tools is None:
        tools = default_tools

    return SkillRuntimePlan(
        session_id=session_id,
        tool_names=tools,
        agent_name=command.agent,
        model_name=command.model,
        temperature=effort_to_temperature(command.effort),
    )


async def resolve_and_build_skill_prefix(
    question: str,
    commands: list[Command],
    *,
    cwd: str,
    session_id: str,
    active_file: str | None = None,
) -> tuple[str, str, ResolvedSkill | None]:
    """解析用户输入中的 slash 技能，生成 system 前缀与有效提问。

    返回示例::

        # 命中 /explain
        prefix, effective_q, resolved = await resolve_and_build_skill_prefix(
            "/explain 装饰器",
            commands,
            cwd="D:/LangChain_Demo",
            session_id="sess-001",
        )
        # prefix      == "请解释 装饰器\\n..."   （技能正文拼接）
        # effective_q == "装饰器"               （去掉 /explain 后的剩余）
        # resolved    == ResolvedSkill(...)

        # 未命中
        prefix, effective_q, resolved = await resolve_and_build_skill_prefix(
            "你好", commands, cwd="...", session_id="s1"
        )
        # prefix == "", effective_q == "你好", resolved is None
    """
    ctx = create_tool_use_context(
        cwd=cwd,
        session_id=session_id,
        permissions=allow_all_permissions(),
        active_file=active_file,
    )
    resolved = await try_resolve_skill(question, commands, ctx)
    if resolved is None:
        return "", question, None

    prefix = "\n\n".join(b.text for b in resolved.blocks)
    effective_q = resolved.remainder_user_text or question
    return prefix, effective_q, resolved
