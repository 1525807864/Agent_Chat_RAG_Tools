"""路径 / frontmatter / 读盘 —— 对应 MyClaude utils.ts

本模块负责：
1. 计算技能目录路径（user / project / policy）
2. 校验技能名
3. 异步 memoize（可选）
4. 解析 SKILL.md 的 YAML frontmatter
5. 扫描目录读取 SKILL.md
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Callable, TypeVar

from skills.types import (
    EffortValue,
    FrontmatterShell,
    SkillContextMode,
    SkillFrontmatterFields,
)

T = TypeVar("T")


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------


def get_claude_config_home_dir() -> Path:
    """获取 Claude 配置根目录。

    优先读环境变量 ``CLAUDE_CONFIG_HOME``，否则回退到 ``~/.claude``。

    返回示例::

        Path("C:/Users/lee/.claude")
        # 若设置了 CLAUDE_CONFIG_HOME=D:/my-claude-config
        Path("D:/my-claude-config")
    """
    env = os.environ.get("CLAUDE_CONFIG_HOME")
    if env:
        return Path(env)
    return Path.home() / ".claude"


def get_managed_skills_dir() -> Path:
    """获取企业策略技能目录（教学简化版）。

    返回示例::

        # Windows
        Path("C:/ProgramData/ClaudeCode/skills")
        # Linux / macOS
        Path("/etc/claude-code/skills")
    """
    if os.name == "nt":
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        return Path(program_data) / "ClaudeCode" / "skills"
    return Path("/etc/claude-code/skills")


def get_project_dirs_up_to_home(target_name: str, cwd: str | Path) -> list[Path]:
    """从 cwd 向上逐级查找 ``<dir>/<target_name>``，直到 home 或盘符根。

    参数:
        target_name: 子路径名，如 ``".claude/skills"``
        cwd: 起始目录

    返回示例::

        # cwd = Path("D:/a/b/c"), target_name = ".claude/skills"
        [
            Path("D:/a/b/c/.claude/skills"),
            Path("D:/a/b/.claude/skills"),
            Path("D:/a/.claude/skills"),
            # ... 直到 home 为止
        ]
    """
    home = Path.home().resolve()
    current = Path(cwd).resolve()
    dirs: list[Path] = []

    while True:
        dirs.append(current / target_name)
        if current == home or current.parent == current:
            break
        current = current.parent

    return dirs


def is_valid_skill_name(name: str) -> bool:
    """校验技能名：小写字母数字，中间可有连字符。

    返回示例::

        is_valid_skill_name("explain")       # True
        is_valid_skill_name("code-review")   # True
        is_valid_skill_name("Explain")       # False（大写非法）
        is_valid_skill_name("code_review")   # False（下划线非法）
        is_valid_skill_name("")              # False
    """
    return bool(re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name))


# ---------------------------------------------------------------------------
# memoize：按参数缓存异步结果
# ---------------------------------------------------------------------------


def memoize_async(fn: Callable[..., Any]) -> Callable[..., Any]:
    """简易异步缓存装饰器：同一参数只执行一次，后续直接返回缓存结果。

    失败时清除缓存，允许下次重试。

    返回示例（装饰后的函数行为）::

        @memoize_async
        async def discover(cwd: str) -> list[str]:
            return ["explain", "review"]

        await discover("D:/proj")  # ["explain", "review"]  （真正执行）
        await discover("D:/proj")  # ["explain", "review"]  （命中缓存，不再扫盘）
    """
    cache: dict[str, Any] = {}

    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        import json

        key = json.dumps(
            {"args": [str(a) for a in args], "kwargs": kwargs},
            sort_keys=True,
        )
        if key in cache:
            return cache[key]

        try:
            result = await fn(*args, **kwargs)
            cache[key] = result
            return result
        except Exception:
            # 失败时删掉 key，允许下次重试；再抛出原始异常
            cache.pop(key, None)
            raise

    return wrapper


# ---------------------------------------------------------------------------
# Frontmatter 解析
# ---------------------------------------------------------------------------


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """从 Markdown 内容中提取 YAML frontmatter 与正文。

    教学版不依赖 PyYAML，只支持：
    - ``key: value``
    - ``key: [a, b]``
    - ``true`` / ``false``

    返回示例::

        content = '''---
        name: explain
        paths: [**/*.py, **/*.ts]
        user_invocable: true
        ---
        请解释 ${topic}
        '''

        parse_frontmatter(content)
        # (
        #   {
        #     "name": "explain",
        #     "paths": ["**/*.py", "**/*.ts"],
        #     "user_invocable": True,
        #   },
        #   "请解释 ${topic}\\n",
        # )

        # 没有 frontmatter 时：
        parse_frontmatter("纯正文")
        # ({}, "纯正文")
    """
    match = re.match(r"^---\r?\n([\s\S]*?)\r?\n---\r?\n?", content)
    if not match:
        return {}, content

    raw = match.group(1)
    body = content[match.end() :]
    frontmatter: dict[str, Any] = {}

    for line in raw.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            continue
        # 注意：用 group(1)/group(2)，不要用 groups(1)（那是带默认值的元组接口）
        key = m.group(1)
        value_raw = m.group(2).strip()

        if value_raw.startswith("[") and value_raw.endswith("]"):
            items = [
                s.strip().strip("\"'")
                for s in value_raw[1:-1].split(",")
                if s.strip()
            ]
            frontmatter[key] = items
        elif value_raw in ("true", "false"):
            frontmatter[key] = value_raw == "true"
        else:
            frontmatter[key] = value_raw.strip("\"'")

    return frontmatter, body


def parse_skill_frontmatter_fields(fm: dict[str, Any]) -> SkillFrontmatterFields:
    """把原始 frontmatter dict 收成强类型字段；非法值直接丢弃为 None。

    返回示例::

        fm = {
            "name": "explain",
            "effort": "high",
            "context": "fork",
            "shell": "powershell",
            "arguments": ["topic"],
            "paths": ["**/*.py"],
            "user_invocable": True,
        }
        parse_skill_frontmatter_fields(fm)
        # SkillFrontmatterFields(
        #   name="explain",
        #   effort=EffortValue.HIGH,
        #   context=SkillContextMode.FORK,
        #   shell="powershell",
        #   arguments=["topic"],
        #   paths=["**/*.py"],
        #   user_invocable=True,
        #   ...
        # )

        # 非法 effort 会被丢弃：
        parse_skill_frontmatter_fields({"effort": "extreme"})
        # SkillFrontmatterFields(effort=None, ...)
    """

    def to_str_list(value: Any) -> list[str] | None:
        if isinstance(value, list):
            return [str(v) for v in value]
        if isinstance(value, str):
            return [value]
        return None

    effort = fm.get("effort")
    effort_val = EffortValue(effort) if effort in ("low", "medium", "high") else None

    shell = fm.get("shell")
    shell_val: FrontmatterShell | None = (
        shell if shell in ("bash", "powershell") else None
    )

    ctx = fm.get("context")
    ctx_val: SkillContextMode | None = (
        SkillContextMode(ctx) if ctx in ("inline", "fork") else None
    )

    desc = fm.get("description")
    if not (isinstance(desc, str) or isinstance(desc, list) or desc is None):
        desc = None

    return SkillFrontmatterFields(
        name=fm.get("name") if isinstance(fm.get("name"), str) else None,
        description=desc,
        when_to_use=(
            fm.get("when_to_use")
            if isinstance(fm.get("when_to_use"), str)
            else None
        ),
        allowed_tools=to_str_list(fm.get("allowed_tools")),
        model=fm.get("model") if isinstance(fm.get("model"), str) else None,
        effort=effort_val,
        user_invocable=(
            fm.get("user_invocable")
            if isinstance(fm.get("user_invocable"), bool)
            else None
        ),
        paths=to_str_list(fm.get("paths")),
        version=fm.get("version") if isinstance(fm.get("version"), str) else None,
        context=ctx_val,
        agent=fm.get("agent") if isinstance(fm.get("agent"), str) else None,
        shell=shell_val,
        arguments=to_str_list(fm.get("arguments")),
    )


async def read_skill_files(base_path: str | Path) -> list[tuple[str, Path]]:
    """扫描技能根目录，读取每个子目录下的 SKILL.md。

    约定目录结构::

        <base_path>/<skill-name>/SKILL.md

    目录不存在 → 返回空列表（正常，不要抛错）。

    返回示例::

        # base_path = Path("D:/LangChain_Demo/data/skills")
        # 且存在 explain/SKILL.md、review/SKILL.md
        [
            ("---\\nname: explain\\n---\\n正文...", Path("D:/.../data/skills/explain")),
            ("---\\nname: review\\n---\\n正文...",  Path("D:/.../data/skills/review")),
        ]

        # 目录不存在时：
        []
    """
    base = Path(base_path)
    results: list[tuple[str, Path]] = []

    if not base.is_dir():
        return results

    for entry in base.iterdir():
        if not entry.is_dir():
            continue
        skill_file = entry / "SKILL.md"
        if not skill_file.is_file():
            continue
        try:
            content = skill_file.read_text(encoding="utf-8")
            results.append((content, entry))
        except OSError:
            # 读失败（权限/编码）跳过该技能，不影响其它技能
            continue

    return results
