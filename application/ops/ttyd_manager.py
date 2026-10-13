"""ttyd 生命周期管理。

干啥的：
  给某个 ops 沙箱开一个网页终端，签个短时 ticket，前端 iframe 只认 ticket。

咋起进程：
  - native：本机直接跑 ttyd（Linux 服务器用这个）
  - wsl：Windows 上用 wsl.exe 进 Linux 再跑 ttyd（开发机推荐）
    原因很简单——Windows 上的 ttyd + docker exec，经常能看见提示符但打不了字。

安全：
  - ttyd 只绑 127.0.0.1，浏览器别直连，走我们同源反代
  - 容器名由 session_id 拼出来，不扔给前端
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from application.ops.ttyd_audit import audit_terminal
from config.settings import get_settings

_log = logging.getLogger("nexora.ops.ttyd")

# 给前端展示用北京时间；内部比较还是 UTC
_BJ = timezone(timedelta(hours=8))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _bj_iso(dt: datetime) -> str:
    return dt.astimezone(_BJ).isoformat()


def container_name_for(session_id: str) -> str:
    """跟 docker_runtime 里拼容器名的规则保持一致。"""
    return f"nexora-sbx-{session_id}"


def _is_wsl_runtime() -> bool:
    """看配置是不是要走 WSL。只有写了 wsl 才走，别的都当 native。"""
    runtime = (get_settings().ops_ttyd_runtime or "native").strip().lower()
    return runtime == "wsl"


@dataclass
class TerminalRecord:
    """一次终端租约。先放进程内存里，以后要多实例再换 Redis。"""

    ticket: str
    terminal_id: str
    tenant_id: str
    user_id: str
    sandbox_session_id: str
    port: int
    pid: int
    created_at: datetime
    expires_at: datetime
    readonly: bool = False
    # Windows 上 uvicorn 常用 SelectorEventLoop，asyncio 子进程不靠谱，所以用 Popen
    process: subprocess.Popen[bytes] | None = field(default=None, repr=False)
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def alive(self) -> bool:
        if self.process is None:
            return False
        # poll() 是 None 说明还在跑
        return self.process.poll() is None

    def expired(self) -> bool:
        return _now() >= self.expires_at

    def public(self) -> dict[str, Any]:
        """给前端看的字段：别带 port / pid / 容器名。"""
        return {
            "terminalId": self.terminal_id,
            "sandboxSessionId": self.sandbox_session_id,
            # 跟 ttyd 的 -b 对上，页面里的 /ws 才不会跑飞
            "terminalUrl": f"/api/ops/terminal/proxy/{self.ticket}/",
            "expiresAt": _bj_iso(self.expires_at),
            "ttlSec": max(0, int((self.expires_at - _now()).total_seconds())),
            "readonly": self.readonly,
            "status": "running" if self.alive and not self.expired() else "stopped",
            # 没开录制就别显示下载按钮
            "recording": bool(self.meta.get("recordingFile")),
        }

    def proxy_base(self) -> str:
        """反代前缀，末尾别带 /。"""
        return f"/api/ops/terminal/proxy/{self.ticket}"


def _build_ttyd_inner_argv(
    *,
    bind: str,
    port: int,
    base_path: str,
    readonly: bool,
    cname: str,
    shell: str,
    recording_file: str,
    typescript_path: str,
) -> list[str]:
    """拼出「ttyd + docker exec …」这一截，还没包 wsl 前缀。"""
    s = get_settings()
    argv: list[str] = [
        s.ops_ttyd_bin,  # wsl 模式下这里是 Linux 路径，比如 /usr/bin/ttyd
        "-i",
        bind,
        "-p",
        str(port),
        "-b",
        base_path,
        "-m",
        "0",  # 0 = 不限制连几个客户端，开发省事
    ]
    # ttyd 1.7+ 默认变成只读了！不显式开 -W，网页上只能看不能敲
    # 我们这里：可写就 -W；只要只读就别加（保持默认只读）
    if not readonly:
        argv.append("-W")
    # 老版本还有 -R；新版本默认只读，加不加都行，留着兼容一下旧二进制
    if readonly:
        argv.append("-R")

    # 注意：别用 docker exec -t。
    # ttyd 自己已经有 PTY 了；再加 -t，在「wsl -e 非交互拉起」时 stdin 经常对不上，
    # 表现就是看得见提示符但打不了字。容器里用 script 弄伪终端就够了。
    ts_path = typescript_path or "/dev/null"
    if not recording_file:
        # 没开录制也写 /dev/null，图的就是 script 给的那层 PTY
        ts_path = "/dev/null"
    argv.extend(
        [
            "docker",
            "exec",
            "-i",
            cname,
            "script",
            "-q",
            "-c",
            shell,
            ts_path,
        ]
    )
    return argv


def _wrap_argv_for_runtime(inner_argv: list[str]) -> list[str]:
    """需要走 WSL 的话，外面再套一层 wsl.exe -d xxx -e …"""
    if not _is_wsl_runtime():
        return inner_argv

    s = get_settings()
    wsl_exe = (s.ops_ttyd_wsl_exe or "wsl").strip() or "wsl"
    distro = (s.ops_ttyd_wsl_distro or "").strip()

    prefix: list[str] = [wsl_exe]
    if distro:
        # 指定发行版，别一不小心跑到没装 ttyd 的那个去了
        prefix.extend(["-d", distro])
    # -e：后面跟的是要在 Linux 里执行的程序和参数，别再套一层 bash -c 折腾转义
    prefix.append("-e")
    return prefix + inner_argv


def _popen_ttyd(argv: list[str]) -> subprocess.Popen[bytes]:
    """真正拉起进程。stderr 留着，挂了好读原因。"""
    return subprocess.Popen(
        argv,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )


def _kill_ttyd_process(rec: TerminalRecord) -> None:
    """关掉这次终端。

    WSL 模式下 Popen 拿到的是 wsl.exe 的 pid，光 terminate 有时候 WSL 里的 ttyd 还活着，
    所以先按端口在 WSL 里 pkill 一把，再收拾 Windows 这边的进程。
    """
    s = get_settings()
    proc = rec.process

    if _is_wsl_runtime():
        wsl_exe = (s.ops_ttyd_wsl_exe or "wsl").strip() or "wsl"
        distro = (s.ops_ttyd_wsl_distro or "").strip()
        kill_argv: list[str] = [wsl_exe]
        if distro:
            kill_argv.extend(["-d", distro])
        # 端口是我们自己分配的 int，拼进命令行没问题
        kill_argv.extend(
            [
                "-e",
                "bash",
                "-c",
                f"pkill -f 'ttyd.*-p {int(rec.port)}' 2>/dev/null || true",
            ]
        )
        try:
            subprocess.run(
                kill_argv,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
            )
        except Exception:
            _log.debug("wsl 里 pkill ttyd 失败了 port=%s", rec.port, exc_info=True)

    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=3.0)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2.0)
        except ProcessLookupError:
            pass


class TtydManager:
    """端口池 + ticket 表 + 子进程。单例用就行。"""

    def __init__(self) -> None:
        self._by_ticket: dict[str, TerminalRecord] = {}
        self._by_terminal: dict[str, TerminalRecord] = {}
        # 关掉之后录制文件元数据还留着，方便下载
        self._archive: dict[str, dict[str, Any]] = {}
        self._lock = asyncio.Lock()

    def _pick_port(self) -> int:
        """在配置的端口段里找一个空的。"""
        s = get_settings()
        lo, hi = int(s.ops_ttyd_port_min), int(s.ops_ttyd_port_max)
        if hi < lo:
            raise RuntimeError("OPS_TTYD_PORT_MAX 比 PORT_MIN 还小，检查一下 .env")
        for port in range(lo, hi + 1):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    # 在 Windows 上绑一下，WSL 转发的也是这套端口，冲突能挡大半
                    sock.bind((s.ops_ttyd_bind, port))
                except OSError:
                    continue
                return port
        raise RuntimeError("ttyd 端口用光了，关掉几个闲置终端，或者把端口范围放大点")

    def _count_user(self, user_id: str) -> int:
        return sum(
            1
            for r in self._by_ticket.values()
            if r.user_id == user_id and r.alive and not r.expired()
        )

    async def open(
        self,
        *,
        tenant_id: str,
        user_id: str,
        sandbox_session_id: str,
        readonly: bool = False,
        approved: bool = False,
    ) -> TerminalRecord:
        """拉起 ttyd，签发 ticket。

        调用方得先搞定：登录、沙箱会话、该审批的已经审批过。
        """
        s = get_settings()
        if not s.ops_ttyd_enabled:
            raise PermissionError("交互终端没开（OPS_TTYD_ENABLED=false）")
        bind = (s.ops_ttyd_bind or "").strip() or "127.0.0.1"
        if bind not in ("127.0.0.1", "::1", "localhost"):
            raise RuntimeError("OPS_TTYD_BIND 只能是 127.0.0.1，别对外裸奔")
        if not sandbox_session_id or len(sandbox_session_id) < 6:
            raise ValueError("sandbox_session_id 不对劲")

        async with self._lock:
            max_per_user = int(s.ops_ttyd_max_per_user)
            # 0 表示不限
            if max_per_user > 0 and self._count_user(user_id) >= max_per_user:
                raise PermissionError(f"一个人最多开 {max_per_user} 个终端")

            port = self._pick_port()
            ticket = secrets.token_urlsafe(32)
            terminal_id = secrets.token_hex(8)
            cname = container_name_for(sandbox_session_id)
            shell = (s.ops_ttyd_shell or "/bin/bash").strip() or "/bin/bash"
            # 这个路径得跟反代一致，否则页面里的 ws/静态资源 404
            base_path = f"/api/ops/terminal/proxy/{ticket}"

            recording_file = ""
            typescript_path = "/dev/null"
            if bool(s.ops_ttyd_recording_enabled):
                await self._ensure_nexora_dir(cname)
                recording_file = f"ttyrec-{terminal_id}.log"
                typescript_path = f"/workspace/.nexora/{recording_file}"

            inner_argv = _build_ttyd_inner_argv(
                bind=bind,
                port=port,
                base_path=base_path,
                readonly=readonly,
                cname=cname,
                shell=shell,
                recording_file=recording_file,
                typescript_path=typescript_path,
            )
            argv = _wrap_argv_for_runtime(inner_argv)

            _log.info(
                "ttyd.start runtime=%s user=%s session=%s port=%s readonly=%s argv0=%s",
                (s.ops_ttyd_runtime or "native"),
                user_id,
                sandbox_session_id,
                port,
                readonly,
                argv[0],
            )

            try:
                proc = await asyncio.to_thread(_popen_ttyd, argv)
            except FileNotFoundError as exc:
                if _is_wsl_runtime():
                    hint = "找不到 wsl.exe，或者 OPS_TTYD_WSL_EXE 写错了"
                else:
                    hint = f"找不到 ttyd：{s.ops_ttyd_bin}，先装好或者改 OPS_TTYD_BIN"
                raise RuntimeError(hint) from exc

            # WSL 第一次起来有点慢，多等半秒
            await asyncio.sleep(0.8 if _is_wsl_runtime() else 0.35)
            if proc.poll() is not None:
                err = b""
                try:
                    _out, err = proc.communicate(timeout=1.0)
                except Exception:
                    err = b""
                msg = (err or b"").decode("utf-8", "replace")[:500]
                # native 老路径：没 script 就再试一次裸 shell（凑合）
                if (
                    not _is_wsl_runtime()
                    and recording_file
                    and "script" in msg.lower()
                ):
                    _log.warning("没有 script，退回普通 shell：%s", msg[:200])
                    recording_file = ""
                    # 单独拼一版裸 docker exec -i，不再套 script
                    fb_argv = [
                        s.ops_ttyd_bin,
                        "-i",
                        bind,
                        "-p",
                        str(port),
                        "-b",
                        base_path,
                        "-m",
                        "0",
                    ]
                    if not readonly:
                        fb_argv.append("-W")
                    if readonly:
                        fb_argv.append("-R")
                    fb_argv.extend(["docker", "exec", "-i", cname, shell])
                    proc = await asyncio.to_thread(_popen_ttyd, fb_argv)
                    await asyncio.sleep(0.35)
                    if proc.poll() is not None:
                        try:
                            _o2, err2 = proc.communicate(timeout=1.0)
                        except Exception:
                            err2 = b""
                        raise RuntimeError(
                            f"ttyd 起不来：{(err2 or b'').decode('utf-8', 'replace')[:400]}"
                        )
                else:
                    raise RuntimeError(
                        f"ttyd 起不来（runtime={s.ops_ttyd_runtime}）："
                        f"{msg or proc.returncode}"
                    )

            ttl = int(s.ops_ttyd_ticket_ttl_sec)
            meta: dict[str, Any] = {
                "approved": approved,
                "runtime": (s.ops_ttyd_runtime or "native"),
            }
            if recording_file:
                meta["recordingFile"] = recording_file
            rec = TerminalRecord(
                ticket=ticket,
                terminal_id=terminal_id,
                tenant_id=tenant_id,
                user_id=user_id,
                sandbox_session_id=sandbox_session_id,
                port=port,
                pid=proc.pid or 0,
                created_at=_now(),
                expires_at=_now() + timedelta(seconds=ttl),
                readonly=readonly,
                process=proc,
                meta=meta,
            )
            self._by_ticket[ticket] = rec
            self._by_terminal[terminal_id] = rec
            audit_terminal(
                "open",
                userId=user_id,
                tenantId=tenant_id,
                terminalId=terminal_id,
                sandboxSessionId=sandbox_session_id,
                readonly=readonly,
                approved=approved,
                recordingFile=recording_file or None,
            )
            return rec

    async def _ensure_nexora_dir(self, container_name: str) -> None:
        """录制目录弄一下，没有就建。"""
        await asyncio.to_thread(
            subprocess.run,
            [
                "docker",
                "exec",
                container_name,
                "mkdir",
                "-p",
                "/workspace/.nexora",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )

    def resolve_ticket(self, ticket: str) -> TerminalRecord:
        """反代进来时验 ticket。"""
        rec = self._by_ticket.get(ticket or "")
        if rec is None:
            raise LookupError("ticket 无效")
        if rec.expired():
            raise PermissionError("ticket 过期了，重新开一个终端吧")
        if not rec.alive:
            raise PermissionError("终端进程已经没了")
        return rec

    def get(self, terminal_id: str, *, user_id: str, tenant_id: str) -> TerminalRecord:
        rec = self._by_terminal.get(terminal_id)
        if rec is None:
            raise LookupError("终端不存在")
        if rec.user_id != user_id or rec.tenant_id != tenant_id:
            # 别让人靠枚举 id 试出来别人的终端
            raise LookupError("终端不存在")
        return rec

    async def close(self, terminal_id: str, *, user_id: str, tenant_id: str) -> None:
        async with self._lock:
            try:
                rec = self.get(terminal_id, user_id=user_id, tenant_id=tenant_id)
            except LookupError:
                return
            await self._kill(rec)

    async def _kill(self, rec: TerminalRecord) -> None:
        await asyncio.to_thread(_kill_ttyd_process, rec)
        if rec.meta.get("recordingFile"):
            self._archive[rec.terminal_id] = {
                "tenant_id": rec.tenant_id,
                "user_id": rec.user_id,
                "sandbox_session_id": rec.sandbox_session_id,
                "recordingFile": rec.meta["recordingFile"],
            }
        self._by_ticket.pop(rec.ticket, None)
        self._by_terminal.pop(rec.terminal_id, None)
        audit_terminal(
            "close",
            userId=rec.user_id,
            tenantId=rec.tenant_id,
            terminalId=rec.terminal_id,
            sandboxSessionId=rec.sandbox_session_id,
            recordingFile=rec.meta.get("recordingFile"),
        )
        _log.info(
            "ttyd.stop terminal=%s session=%s user=%s",
            rec.terminal_id,
            rec.sandbox_session_id,
            rec.user_id,
        )

    def recording_meta(
        self, terminal_id: str, *, user_id: str, tenant_id: str
    ) -> dict[str, Any]:
        """查录制文件信息：进行中的，或者关掉之后归档的。"""
        rec = self._by_terminal.get(terminal_id)
        if rec is not None:
            if rec.user_id != user_id or rec.tenant_id != tenant_id:
                raise LookupError("终端不存在")
            name = rec.meta.get("recordingFile")
            if not name:
                raise LookupError("本会话未开启录制")
            return {
                "sandbox_session_id": rec.sandbox_session_id,
                "recordingFile": name,
                "tenant_id": rec.tenant_id,
            }
        archived = self._archive.get(terminal_id)
        if archived is None:
            raise LookupError("终端不存在")
        if archived.get("user_id") != user_id or archived.get("tenant_id") != tenant_id:
            raise LookupError("终端不存在")
        return archived

    async def close_by_sandbox(self, sandbox_session_id: str) -> int:
        """沙箱释放时，把挂在上面的终端一块关掉。"""
        async with self._lock:
            targets = [
                r
                for r in list(self._by_ticket.values())
                if r.sandbox_session_id == sandbox_session_id
            ]
            for rec in targets:
                await self._kill(rec)
            return len(targets)

    async def reap_expired(self) -> int:
        """扫一遍过期的、已经死掉的，清掉。"""
        dead: list[TerminalRecord] = []
        async with self._lock:
            for rec in list(self._by_ticket.values()):
                if rec.expired() or not rec.alive:
                    dead.append(rec)
            for rec in dead:
                await self._kill(rec)
        return len(dead)


_manager: TtydManager | None = None


def get_ttyd_manager() -> TtydManager:
    global _manager
    if _manager is None:
        _manager = TtydManager()
    return _manager
