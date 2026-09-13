"""Skills 子系统公开 API。

快速上手::

    from skills import discover_skills, try_resolve_skill, create_tool_use_context

    cmds = await discover_skills(cwd=".", demo_skills_dir=Path("data/skills"))
    ctx = create_tool_use_context(cwd=".", session_id="s1")
    resolved = await try_resolve_skill("/explain 装饰器", cmds, ctx)
    # resolved.blocks[0].text → 注入给 LLM 的技能正文
"""

from skills.create_skill import create_skill_command
from skills.integrate_hooks import (
    SkillRuntimePlan,
    build_runtime_plan,
    effort_to_temperature,
    resolve_and_build_skill_prefix,
)
from skills.load_skills import SOURCE_RANK, discover_skills, pick_by_priority, skill_file_to_command
from skills.path_match import is_skill_active_for_path, match_glob
from skills.permissions import (
    PatternPermissionChecker,
    allow_all_permissions,
    create_tool_use_context,
    deny_all_permissions,
)
from skills.resolve import ResolvedSkill, try_resolve_skill
from skills.substitute import expand_builtin_variables, substitute_arguments
from skills.types import (
    Command,
    EffortValue,
    MalformedCommandError,
    PromptContentBlock,
    SkillContextMode,
    SkillFrontmatterFields,
    SkillLoadedFrom,
    ToolUseContext,
)
from skills.utils import (
    get_claude_config_home_dir,
    get_managed_skills_dir,
    get_project_dirs_up_to_home,
    is_valid_skill_name,
    parse_frontmatter,
    parse_skill_frontmatter_fields,
    read_skill_files,
)

__all__ = [
    # types
    "Command",
    "EffortValue",
    "MalformedCommandError",
    "PromptContentBlock",
    "SkillContextMode",
    "SkillFrontmatterFields",
    "SkillLoadedFrom",
    "ToolUseContext",
    # utils
    "get_claude_config_home_dir",
    "get_managed_skills_dir",
    "get_project_dirs_up_to_home",
    "is_valid_skill_name",
    "parse_frontmatter",
    "parse_skill_frontmatter_fields",
    "read_skill_files",
    # substitute
    "substitute_arguments",
    "expand_builtin_variables",
    # create / load
    "create_skill_command",
    "SOURCE_RANK",
    "discover_skills",
    "pick_by_priority",
    "skill_file_to_command",
    # path / permissions / resolve
    "is_skill_active_for_path",
    "match_glob",
    "PatternPermissionChecker",
    "allow_all_permissions",
    "deny_all_permissions",
    "create_tool_use_context",
    "ResolvedSkill",
    "try_resolve_skill",
    # hooks
    "SkillRuntimePlan",
    "build_runtime_plan",
    "effort_to_temperature",
    "resolve_and_build_skill_prefix",
]
