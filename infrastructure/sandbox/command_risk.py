"""高危命令启发式（Approval 层）。

说明
====
- 这是「跑之前」的字符串/argv 判断，拦不住伪装；真正安全靠容器 + 代理。
- 对齐 Claude Code：permission 决策 + sandbox 强制 两层分离。
"""

from __future__ import annotations

import re

from infrastructure.sandbox.models import ExecRequest, SandboxPolicySnapshot

# 明显危险模式（可继续加，但保持可解释）
_RISKY = [
    re.compile(r"\brm\s+(-[a-zA-Z]*f|-[a-zA-Z]*r)", re.I),
    re.compile(r"\bmkfs\b|\bdd\s+if=", re.I),
    re.compile(r"curl\s+[^\n]*\|\s*(ba)?sh", re.I),
    re.compile(r"wget\s+[^\n]*\|\s*(ba)?sh", re.I),
    re.compile(r"\bchmod\s+777\b", re.I),
    re.compile(r":\(\)\s*\{\s*:\|:\s*&\s*\}\s*;", re.I),  # fork bomb
    re.compile(r"\bpowershell\b.*-enc", re.I),
    re.compile(r"Invoke-Expression|IEX\s*\(", re.I),
]


def assess_risk(req: ExecRequest, policy: SandboxPolicySnapshot) -> tuple[bool, str]:
    """返回 (needs_approval, reason)。已 approved 的请求不再拦截。"""
    if req.approved:
        return False, ""
    mode = (policy.approval or "on-risky").strip().lower()
    if mode == "never":
        return False, ""
    if mode == "always" and req.kind in {"shell", "pwsh"}:
        return True, "approval=always：命令需人工确认"
    if mode != "on-risky":
        return False, ""

    blob = " ".join(req.argv) if req.argv else (req.content or req.path or "")
    for pat in _RISKY:
        if pat.search(blob):
            return True, f"匹配高危模式: {pat.pattern[:60]}"
    # 禁止 shell 字符串时，含元字符需审批
    if req.kind in {"shell", "pwsh"} and not policy.allow_shell_string:
        joined = " ".join(req.argv)
        if any(ch in joined for ch in "|><;&`$"):
            return True, "未开启 allow_shell_string，管道/重定向需审批或改 argv"
    return False, ""
