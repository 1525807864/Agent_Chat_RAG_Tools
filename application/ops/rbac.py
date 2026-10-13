"""Ops 终端角色（P3 轻量版）。

规则
====
- 全员可开只读终端（ttyd -R）
- 可写终端：拒绝 user_id 以 ``_guest`` 结尾，或命中 OPS 拒绝名单
- 后续可换成 data/ops/members.json；此处先不建表，避免阻塞联调
"""

from __future__ import annotations

from config.settings import get_settings


def can_open_terminal(user_id: str, *, readonly: bool) -> bool:
    """是否允许打开终端。只读永远更宽松。"""
    uid = (user_id or "").strip()
    if not uid:
        return False
    if readonly:
        return True
    # 访客账号禁止可写交互 shell
    if uid.lower().endswith("_guest"):
        return False
    # 可选：.env 里 OPS_TTYD_DENY_USERS=a,b,c
    deny = getattr(get_settings(), "ops_ttyd_deny_users", "") or ""
    blocked = {x.strip().lower() for x in str(deny).split(",") if x.strip()}
    if uid.lower() in blocked:
        return False
    return True
