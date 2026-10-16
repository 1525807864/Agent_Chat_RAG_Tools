"""用户名规则：登录/注册/建库共用，只 strip，绝不 lower/casefold。"""

from __future__ import annotations

import re

# 首字母英文，避免租户 sanitize 后挤进 default；长度 3–32
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_-]{2,31}$")

USERNAME_RULE_MSG = (
    "用户名须以字母开头，仅含字母、数字、下划线和中横线，长度 3–32"
)


def normalize_new_username(username: str) -> str:
    """注册/建用户：格式校验 + strip，保留原始大小写。"""
    name = (username or "").strip()
    if not USERNAME_RE.fullmatch(name):
        raise ValueError(USERNAME_RULE_MSG)
    return name
