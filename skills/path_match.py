"""条件技能路径匹配 —— 对应 MyClaude pathMatch.ts

frontmatter.paths 为 glob 列表；匹配当前打开文件才激活技能。
教学版只支持 ``*``（单段）和 ``**``（跨目录）。
"""

from __future__ import annotations

import re

from skills.types import Command


def _to_posix(path: str) -> str:
    """把 Windows 反斜杠统一成正斜杠，方便 glob 匹配。

    返回示例::

        _to_posix(r"src\\app.py")  # "src/app.py"
        _to_posix("src/app.py")    # "src/app.py"
    """
    return path.replace("\\", "/")


def glob_to_regexp(glob: str) -> re.Pattern[str]:
    """把简单 glob 转成正则。

    规则:
        - ``*``  = 单段（不含 ``/``）
        - ``**`` = 跨目录任意字符

    返回示例::

        glob_to_regexp("**/*.py")
        # re.compile("^.*[^/]*\\.py$")  之类的 Pattern

        glob_to_regexp("src/*.ts").pattern
        # "^src/[^/]*\\.ts$"
    """
    normalized = _to_posix(glob).lstrip("./")
    pattern: list[str] = []
    i = 0
    while i < len(normalized):
        ch = normalized[i]
        if ch == "*" and i + 1 < len(normalized) and normalized[i + 1] == "*":
            pattern.append(".*")
            i += 2
            if i < len(normalized) and normalized[i] == "/":
                i += 1
            continue
        if ch == "*":
            pattern.append("[^/]*")
        elif ch in r"\.[]{}()+-^$|?":
            pattern.append("\\" + ch)
        else:
            pattern.append(ch)
        i += 1
    return re.compile("^" + "".join(pattern) + "$")


def match_glob(glob: str, file_path: str) -> bool:
    """判断 file_path 是否匹配 glob（也尝试匹配 basename）。

    返回示例::

        match_glob("**/*.py", "src/app.py")     # True
        match_glob("**/*.py", "app.py")         # True（basename）
        match_glob("**/*.ts", "src/app.py")     # False
        match_glob("src/*.py", "src/app.py")    # True
        match_glob("src/*.py", "lib/app.py")    # False
    """
    path = _to_posix(file_path)
    re_pat = glob_to_regexp(glob)
    basename = path.rsplit("/", 1)[-1]
    return bool(re_pat.match(path) or re_pat.match(basename))


def is_skill_active_for_path(command: Command, file_path: str | None) -> bool:
    """判断技能在当前文件上下文是否可用。

    - 没有 ``paths`` → 始终可用
    - 有 ``paths`` → 必须给出 file_path 且命中其中一个 glob

    返回示例::

        # command.paths is None
        is_skill_active_for_path(cmd, None)           # True
        is_skill_active_for_path(cmd, "a.py")         # True

        # command.paths = ["**/*.py"]
        is_skill_active_for_path(cmd, "src/a.py")     # True
        is_skill_active_for_path(cmd, "src/a.ts")     # False
        is_skill_active_for_path(cmd, None)           # False
    """
    if not command.paths:
        return True
    if not file_path:
        return False
    return any(match_glob(g, file_path) for g in command.paths)
