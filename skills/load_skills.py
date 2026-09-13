"""多来源发现 + 优先级合并 —— 对应 MyClaude loadSkills.ts

扫描顺序（先收集，最后按 SOURCE_RANK 去重）::

    1. MCP（最低信任）
    2. user ~/.claude/skills
    3. project 向上找 .claude/skills + 可选 demo_skills_dir
    4. policy 企业目录（最高信任）
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from skills.create_skill import create_skill_command
from skills.types import Command, SkillLoadedFrom
from skills.utils import (
    get_claude_config_home_dir,
    get_managed_skills_dir,
    get_project_dirs_up_to_home,
    is_valid_skill_name,
    parse_frontmatter,
    parse_skill_frontmatter_fields,
    read_skill_files,
)

# 数字越大优先级越高（同名时留下更大的）
SOURCE_RANK: dict[SkillLoadedFrom, int] = {
    SkillLoadedFrom.MCP: 0,
    SkillLoadedFrom.USER: 1,
    SkillLoadedFrom.PROJECT: 2,
    SkillLoadedFrom.POLICY: 3,
}


def skill_file_to_command(
    content: str,
    skill_dir: Path,
    loaded_from: SkillLoadedFrom,
    logger: Optional[Callable[[str], None]] = None,
    *,
    enable_shell: bool = False,
) -> Command | None:
    """单份 SKILL.md 文本 → Command；非法名返回 None。

    返回示例::

        content = '''---
        name: explain
        arguments: [topic]
        ---
        请解释 ${topic}
        '''
        skill_file_to_command(content, Path(".../explain"), SkillLoadedFrom.PROJECT)
        # Command(name="explain", loaded_from=PROJECT, ...)

        # 非法名：
        skill_file_to_command("---\\nname: Bad_Name\\n---\\nx", Path("..."), ...)
        # None
    """
    fm_raw, body = parse_frontmatter(content)
    fields = parse_skill_frontmatter_fields(fm_raw)

    skill_name = fields.name or skill_dir.name
    if not is_valid_skill_name(skill_name):
        if logger:
            logger(f"skip invalid skill name: {skill_name} ({skill_dir})")
        return None

    return create_skill_command(
        skill_name=skill_name,
        markdown_content=body,
        loaded_from=loaded_from,
        fields=fields,
        base_dir=str(skill_dir),
        enable_shell=enable_shell,
    )


def pick_by_priority(commands: list[Command]) -> list[Command]:
    """同名技能保留更高信任来源。

    返回示例::

        # 同名 explain：user 与 project 各一份
        pick_by_priority([user_explain, project_explain])
        # [project_explain]   # PROJECT 信任更高

        # 不同名：
        pick_by_priority([explain_cmd, review_cmd])
        # [explain_cmd, review_cmd]  （顺序不保证，以 dict 插入为准）
    """
    best: dict[str, Command] = {}
    for cmd in commands:
        prev = best.get(cmd.name)
        if prev is None or SOURCE_RANK[cmd.loaded_from] >= SOURCE_RANK[prev.loaded_from]:
            best[cmd.name] = cmd
    return list(best.values())


async def discover_skills(
    *,
    cwd: str | Path,
    user_skills_dir: Path | None = None,
    project_skills_dirs: list[Path] | None = None,
    policy_skills_dir: Path | None = None,
    demo_skills_dir: Path | None = None,
    mcp_skills: list[tuple[str, str]] | None = None,
    logger: Optional[Callable[[str], None]] = None,
    enable_shell: bool = False,
) -> list[Command]:
    """扫描各来源并按优先级去重，返回可用 Command 列表。

    参数:
        cwd: 当前工作目录（用于向上找项目技能）
        user_skills_dir: 覆盖 ``~/.claude/skills``（单测用）
        project_skills_dirs: 覆盖项目技能目录列表
        policy_skills_dir: 覆盖企业策略目录
        demo_skills_dir: 额外项目技能根，如 ``data/skills``
        mcp_skills: ``[(content, name), ...]`` MCP 下发的技能原文
        enable_shell: 是否允许技能内嵌 Shell（默认关）

    返回示例::

        cmds = await discover_skills(
            cwd="D:/LangChain_Demo",
            demo_skills_dir=Path("D:/LangChain_Demo/data/skills"),
        )
        # [
        #   Command(name="explain", loaded_from=PROJECT, ...),
        #   Command(name="review",  loaded_from=PROJECT, ...),
        # ]

        # 无任何技能目录时：
        # []
    """
    collected: list[Command] = []

    # ---- 1. MCP（最低信任）----
    for content, name in mcp_skills or []:
        fake_dir = Path(f"mcp://{name}")
        cmd = skill_file_to_command(
            content, fake_dir, SkillLoadedFrom.MCP, logger, enable_shell=enable_shell
        )
        if cmd:
            collected.append(cmd)

    # ---- 2. user ----
    user_dir = user_skills_dir or (get_claude_config_home_dir() / "skills")
    for content, d in await read_skill_files(user_dir):
        cmd = skill_file_to_command(
            content, d, SkillLoadedFrom.USER, logger, enable_shell=enable_shell
        )
        if cmd:
            collected.append(cmd)

    # ---- 3. project（含可选 demo_skills_dir）----
    project_dirs = project_skills_dirs or get_project_dirs_up_to_home(
        ".claude/skills", cwd
    )
    if demo_skills_dir is not None:
        project_dirs = [demo_skills_dir, *project_dirs]

    for pdir in project_dirs:
        for content, d in await read_skill_files(pdir):
            cmd = skill_file_to_command(
                content, d, SkillLoadedFrom.PROJECT, logger, enable_shell=enable_shell
            )
            if cmd:
                collected.append(cmd)

    # ---- 4. policy ----
    policy_dir = policy_skills_dir or get_managed_skills_dir()
    for content, d in await read_skill_files(policy_dir):
        cmd = skill_file_to_command(
            content, d, SkillLoadedFrom.POLICY, logger, enable_shell=enable_shell
        )
        if cmd:
            collected.append(cmd)

    return pick_by_priority(collected)
