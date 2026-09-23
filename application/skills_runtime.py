"""Skills 懒加载与本轮 slash 解析（不扫描 ~/.claude/skills）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any


class SkillsRuntime:
    """挂在 AgentApplication 上：ensure + resolve_for_turn。"""

    def __init__(self, project_root: Path, logger: Any) -> None:
        self._root = project_root
        self._logger = logger
        self._skills = None

    async def ensure(self):
        if self._skills is not None:
            return self._skills

        from skills.load_skills import discover_skills

        demo_dir = self._root / "data" / "skills"
        project_claude = self._root / ".claude" / "skills"
        project_dirs = [project_claude] if project_claude.is_dir() else []

        self._skills = await discover_skills(
            cwd=str(self._root),
            user_skills_dir=Path("__skills_user_disabled__"),
            policy_skills_dir=Path("__skills_policy_disabled__"),
            project_skills_dirs=project_dirs,
            demo_skills_dir=demo_dir if demo_dir.is_dir() else None,
            logger=lambda m: self._logger.info("[skills] %s", m),
            enable_shell=False,
        )
        self._logger.info(
            "Skills 已加载: %s",
            [c.name for c in self._skills] if self._skills else [],
        )
        return self._skills

    async def resolve_for_turn(
        self,
        user_input: str,
        session_id: str,
        *,
        active_file: str | None = None,
    ) -> tuple[str, str, str, object | None, float | None, str | None]:
        """返回 (effective_input, skill_extra, memory_session_id, resolved, temp, model)。"""
        from shared.errors import AppError, ErrorCode
        from skills.integrate_hooks import (
            build_runtime_plan,
            resolve_and_build_skill_prefix,
        )
        from skills.types import MalformedCommandError

        skills = await self.ensure()
        try:
            prefix, effective_q, resolved = await resolve_and_build_skill_prefix(
                user_input,
                skills,
                cwd=str(self._root),
                session_id=session_id,
                active_file=active_file,
            )
        except MalformedCommandError as e:
            raise AppError(
                ErrorCode.VALIDATION,
                f"技能执行失败: {e}",
                http_status=400,
            ) from e

        if resolved is None:
            return user_input, "", session_id, None, None, None

        plan = build_runtime_plan(resolved.command, base_session_id=session_id)
        skill_extra = ""
        if prefix.strip():
            skill_extra = (
                f"\n\n# Active Skill: /{resolved.command.name}\n"
                f"请严格遵循下列技能说明完成用户请求：\n\n{prefix.strip()}\n"
            )
        self._logger.info(
            "Skill 激活: /%s args=%s session=%s",
            resolved.command.name,
            resolved.args,
            plan.session_id,
        )
        return (
            effective_q,
            skill_extra,
            plan.session_id,
            resolved,
            plan.temperature,
            plan.model_name,
        )
