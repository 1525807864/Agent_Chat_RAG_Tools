"""沙箱工作区文件工具（宿主机侧安全读写）。

设计
====
- 路径必须落在 session.workspace_host 内，防 .. 穿越。
- 读/写在宿主机完成，避免再走 bash cat/echo（减少注入面）。
- 容器内同一目录已 bind 到 /workspace，Agent 看到的路径用 /workspace 相对语义。
"""

from __future__ import annotations

import time
from pathlib import Path

from infrastructure.sandbox.models import ExecRequest, ExecResult, SandboxSession


def _resolve(session: SandboxSession, rel: str) -> Path:
    """把 /workspace/xxx 或相对路径映射到宿主机绝对路径。"""
    raw = (rel or "").replace("\\", "/").strip()
    if raw.startswith("/workspace/"):
        raw = raw[len("/workspace/") :]
    elif raw == "/workspace":
        raw = ""
    elif raw.startswith("/"):
        raise PermissionError("只允许访问 /workspace 下路径")
    base = Path(session.workspace_host).resolve()
    target = (base / raw).resolve()
    if base != target and base not in target.parents:
        raise PermissionError("路径越出工作区")
    return target


def fs_list(session: SandboxSession, req: ExecRequest) -> ExecResult:
    t0 = time.perf_counter()
    try:
        path = _resolve(session, req.path or "/workspace")
        if not path.exists():
            return _fail("目录不存在", t0)
        if not path.is_dir():
            return _fail("不是目录", t0)
        names = sorted(p.name + ("/" if p.is_dir() else "") for p in path.iterdir())
        return _ok("\n".join(names), t0)
    except PermissionError as exc:
        return _fail(str(exc), t0)


def fs_read(session: SandboxSession, req: ExecRequest) -> ExecResult:
    t0 = time.perf_counter()
    try:
        path = _resolve(session, req.path)
        if not path.is_file():
            return _fail("文件不存在", t0)
        data = path.read_bytes()
        limit = session.limits.max_output_bytes
        trunc = len(data) > limit
        text = data[:limit].decode("utf-8", "replace")
        if trunc:
            text += "\n<truncated>"
        return ExecResult(
            ok=True,
            exit_code=0,
            stdout=text,
            stderr="",
            truncated=trunc,
            duration_ms=_ms(t0),
        )
    except PermissionError as exc:
        return _fail(str(exc), t0)


def fs_write(session: SandboxSession, req: ExecRequest) -> ExecResult:
    t0 = time.perf_counter()
    try:
        if session.policy.mode == "read-only":
            return _fail("read-only 会话禁止写入", t0)
        path = _resolve(session, req.path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(req.content or "", encoding="utf-8")
        return _ok(f"wrote {len(req.content or '')} bytes", t0)
    except PermissionError as exc:
        return _fail(str(exc), t0)


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _ok(stdout: str, t0: float) -> ExecResult:
    return ExecResult(
        ok=True,
        exit_code=0,
        stdout=stdout,
        stderr="",
        truncated=False,
        duration_ms=_ms(t0),
    )


def _fail(msg: str, t0: float) -> ExecResult:
    return ExecResult(
        ok=False,
        exit_code=1,
        stdout="",
        stderr=msg,
        truncated=False,
        duration_ms=_ms(t0),
    )
