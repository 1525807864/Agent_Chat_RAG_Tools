"""路径沙箱：限制读文件 / 知识库目录落在配置允许的根目录内。

商业与安全边界
==============
- ``read_file``、``doc_dir`` 不得任意访问系统盘。
- 默认允许项目下的 ``data/``；可通过 Settings.allowed_data_roots 扩展。
- 解析时使用 ``resolve()`` + ``relative_to``，抵御 ``..`` 穿越。
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence


class PathSecurityError(ValueError):
    """路径不在白名单根目录内，或目标非法。"""


def get_project_root(explicit: str | Path | None = None) -> Path:
    """解析项目根目录。

    默认取本文件上两级（``shared/`` → 仓库根）。测试时可传入 explicit。
    """
    if explicit is not None:
        return Path(explicit).resolve()
    return Path(__file__).resolve().parent.parent


def normalize_allowed_roots(
    roots: Sequence[str | Path],
    project_root: Path | None = None,
) -> list[Path]:
    """把相对根转为绝对路径并去重。"""
    base = project_root or get_project_root()
    resolved: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        p = Path(root)
        abs_root = (p if p.is_absolute() else (base / p)).resolve()
        key = str(abs_root)
        if key not in seen:
            seen.add(key)
            resolved.append(abs_root)
    return resolved


def resolve_safe_path(
    user_path: str | Path,
    *,
    allowed_roots: Sequence[str | Path],
    project_root: Path | None = None,
    must_exist: bool = False,
    expect_dir: bool | None = None,
) -> Path:
    """将用户提供的路径解析到白名单根下。

    Parameters
    ----------
    user_path:
        相对路径相对于 ``project_root`` 解析；绝对路径必须落在某个 allowed_root 内。
    must_exist:
        True 时路径必须已存在。
    expect_dir:
        True/False 分别要求目录/文件；None 不校验类型。

    Raises
    ------
    PathSecurityError
        路径穿越或越权。
    """
    base = project_root or get_project_root()
    roots = normalize_allowed_roots(allowed_roots, base)
    if not roots:
        raise PathSecurityError("未配置任何允许的路径根目录")

    raw = Path(user_path)
    candidate = (raw if raw.is_absolute() else (base / raw)).resolve()

    if not any(_is_relative_to(candidate, root) for root in roots):
        raise PathSecurityError(
            f"路径不在允许范围内: {user_path}（允许根: {[str(r) for r in roots]}）"
        )

    if must_exist and not candidate.exists():
        raise PathSecurityError(f"路径不存在: {user_path}")

    if expect_dir is True and candidate.exists() and not candidate.is_dir():
        raise PathSecurityError(f"期望目录但得到文件: {user_path}")
    if expect_dir is False and candidate.exists() and not candidate.is_file():
        raise PathSecurityError(f"期望文件但得到目录: {user_path}")

    return candidate


def _is_relative_to(path: Path, root: Path) -> bool:
    """兼容 Python 3.8+ 的 relative_to 判断。"""
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
