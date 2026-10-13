"""Docker 实现：一台短生命周期容器 = 一台沙箱电脑。

硬约束
======
- 非交互：docker exec + argv；默认禁止 bash -lc。
- 资源 / cap-drop / 只读根 / no-new-privileges。
- 网络：deny→none；allowlist/open→bridge + HTTP_PROXY 指向宿主机 egress。

Windows 注意
============
uvicorn 在 Windows 上常用 SelectorEventLoop，不支持
``asyncio.create_subprocess_exec``（会 NotImplementedError）。
因此 docker CLI 一律走 ``asyncio.to_thread(subprocess.run/Popen)``。
"""

from __future__ import annotations

import asyncio
import logging
import subprocess
import time
from pathlib import Path

from infrastructure.sandbox.models import (
    ExecRequest,
    ExecResult,
    SandboxLimits,
    SandboxSession,
)
from infrastructure.sandbox.runtime import SandboxRuntime

_log = logging.getLogger(__name__)


def _run_docker(args: list[str], *, timeout: float | None = None) -> subprocess.CompletedProcess[bytes]:
    """在工作线程里跑 docker，兼容 Windows SelectorEventLoop。"""
    return subprocess.run(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


class DockerSandboxRuntime(SandboxRuntime):
    """通过本机 docker CLI 管理沙箱容器。"""

    def __init__(self, *, image: str, default_network: str = "none") -> None:
        self._image = image
        self._default_network = default_network

    def _container_name(self, session_id: str) -> str:
        return f"nexora-sbx-{session_id}"

    async def create(
        self,
        *,
        session_id: str,
        tenant_id: str,
        caps: frozenset[str],
        limits: SandboxLimits,
        workspace_host: str,
        network: str,
        proxy_url: str = "",
    ) -> str:
        host = Path(workspace_host)
        host.mkdir(parents=True, exist_ok=True)
        name = self._container_name(session_id)
        use_net = (network or "none") not in ("", "none")
        net = "bridge" if use_net else "none"
        args = [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--memory",
            limits.memory,
            "--cpus",
            str(limits.cpus),
            "--pids-limit",
            str(limits.pids),
            "--read-only",
            "--tmpfs",
            "/tmp:rw,noexec,nosuid,size=64m",
            "--mount",
            f"type=bind,src={host.resolve()},dst=/workspace",
            "--user",
            "1000:1000",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--network",
            net,
        ]
        if use_net and proxy_url:
            args += [
                "--add-host",
                "host.docker.internal:host-gateway",
                "-e",
                f"HTTP_PROXY={proxy_url}",
                "-e",
                f"HTTPS_PROXY={proxy_url}",
                "-e",
                f"http_proxy={proxy_url}",
                "-e",
                f"https_proxy={proxy_url}",
                "-e",
                "NO_PROXY=localhost,127.0.0.1",
            ]
        args.append(self._image)

        try:
            completed = await asyncio.to_thread(_run_docker, args, timeout=120.0)
        except FileNotFoundError as exc:
            raise RuntimeError("找不到 docker 命令，请确认 Docker Desktop 已安装并在 PATH 中") from exc
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError("docker run 超时") from exc

        if completed.returncode != 0:
            msg = (completed.stderr or completed.stdout).decode("utf-8", "replace")[:400]
            raise RuntimeError(f"无法创建沙箱: {msg}")
        cid = (completed.stdout.decode("utf-8", "replace") or name).strip()
        _log.info(
            "sandbox.docker.create name=%s tenant=%s net=%s proxy=%s",
            name,
            tenant_id,
            net,
            bool(proxy_url),
        )
        return cid or name

    async def exec(
        self,
        session: SandboxSession,
        req: ExecRequest,
        *,
        allow_shell_string: bool = False,
    ) -> ExecResult:
        timeout = req.timeout_sec or session.limits.exec_timeout_sec
        name = self._container_name(session.id)

        if not req.argv:
            raise PermissionError("argv 不能为空")

        if req.kind == "pwsh":
            if allow_shell_string or len(req.argv) == 1:
                inner = [
                    "pwsh",
                    "-NoLogo",
                    "-NonInteractive",
                    "-Command",
                    " ".join(req.argv),
                ]
            else:
                inner = [
                    "pwsh",
                    "-NoLogo",
                    "-NonInteractive",
                    "-Command",
                    "--",
                    *req.argv,
                ]
        else:
            if allow_shell_string and (len(req.argv) == 1 or _needs_shell(req.argv)):
                inner = ["bash", "-lc", " ".join(req.argv)]
            else:
                if _needs_shell(req.argv) and not allow_shell_string:
                    raise PermissionError(
                        "禁止 shell 元字符，请传纯 argv 或开启审批/allow_shell_string"
                    )
                inner = list(req.argv)

        args = [
            "docker",
            "exec",
            "-u",
            "1000:1000",
            "-w",
            _safe_cwd(req.cwd),
            name,
            *inner,
        ]
        t0 = time.perf_counter()
        timed_out = False
        try:
            completed = await asyncio.to_thread(
                _run_docker, args, timeout=float(timeout)
            )
            out_b, err_b = completed.stdout or b"", completed.stderr or b""
            code = int(completed.returncode or 0)
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            out_b = exc.stdout or b""
            err_b = exc.stderr or b""
            code = 124
        except FileNotFoundError as exc:
            raise RuntimeError("找不到 docker 命令") from exc

        max_n = session.limits.max_output_bytes
        stdout, t1 = _clip(out_b, max_n)
        stderr, t2 = _clip(err_b, max_n)
        ms = int((time.perf_counter() - t0) * 1000)
        return ExecResult(
            ok=code == 0 and not timed_out,
            exit_code=code,
            stdout=stdout,
            stderr=stderr,
            truncated=t1 or t2,
            duration_ms=ms,
            timed_out=timed_out,
        )

    async def destroy(self, session: SandboxSession) -> None:
        name = self._container_name(session.id)
        try:
            await asyncio.to_thread(
                _run_docker, ["docker", "rm", "-f", name], timeout=60.0
            )
        except Exception:  # noqa: BLE001
            _log.debug("sandbox.docker.destroy failed name=%s", name, exc_info=True)


def _safe_cwd(cwd: str) -> str:
    raw = (cwd or "/workspace").replace("\\", "/")
    if not raw.startswith("/workspace"):
        return "/workspace"
    if ".." in raw.split("/"):
        return "/workspace"
    return raw


def _needs_shell(argv: list[str]) -> bool:
    if not argv:
        return True
    blob = " ".join(argv)
    return any(ch in blob for ch in "|><;&`$")


def _clip(raw: bytes, limit: int) -> tuple[str, bool]:
    text = (raw or b"").decode("utf-8", "replace")
    if len(text.encode("utf-8")) <= limit:
        return text, False
    buf = text.encode("utf-8")[:limit]
    return buf.decode("utf-8", "replace") + "\n<truncated>", True
