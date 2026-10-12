"""出站域名白名单代理（对齐 Claude Code / Codex network proxy）。

P0 实现
=======
- 极简 HTTP CONNECT / 明文 HTTP 代理，跑在宿主机。
- 容器通过 HTTP_PROXY/HTTPS_PROXY 访问；非白名单 Host 直接拒绝。
- 生产可换成 Squid；本模块接口保持 start/stop/allow 不变。

注意：这是策略强制层，不是「开了 bridge 就算有网」。
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Iterable

_log = logging.getLogger("nexora.sandbox.egress")

_HOST = re.compile(rb"^(?:[A-Za-z]+)\s+(?:https?://)?([^/:\s]+)", re.I)
_CONNECT = re.compile(rb"^CONNECT\s+([^:\s]+):(\d+)", re.I)


class EgressProxy:
    """进程内单例代理。"""

    def __init__(self, port: int, allowlist: Iterable[str]) -> None:
        self._port = port
        self._allow = {a.strip().lower().lstrip(".") for a in allowlist if a.strip()}
        self._server: asyncio.AbstractServer | None = None

    @property
    def port(self) -> int:
        return self._port

    def allowed(self, host: str) -> bool:
        h = (host or "").lower().strip(".")
        if not h or not self._allow:
            return False
        for rule in self._allow:
            if h == rule or h.endswith("." + rule):
                return True
        return False

    async def start(self) -> None:
        if self._server:
            return
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", self._port)
        _log.info("sandbox.egress.listen port=%s allow=%s", self._port, sorted(self._allow))

    async def stop(self) -> None:
        if not self._server:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            first = await reader.readline()
            if not first:
                writer.close()
                return
            host = ""
            port = 80
            m = _CONNECT.match(first)
            if m:
                host = m.group(1).decode("ascii", "replace")
                port = int(m.group(2))
                # 读完请求头
                while True:
                    line = await reader.readline()
                    if line in (b"\r\n", b"\n", b""):
                        break
                if not self.allowed(host):
                    writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                    await writer.drain()
                    writer.close()
                    return
                remote_r, remote_w = await asyncio.open_connection(host, port)
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
                await writer.drain()
                await asyncio.gather(
                    _pipe(reader, remote_w),
                    _pipe(remote_r, writer),
                )
                return

            hm = _HOST.match(first)
            host = hm.group(1).decode("ascii", "replace") if hm else ""
            if not self.allowed(host):
                writer.write(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                await writer.drain()
                writer.close()
                return
            # 明文 HTTP：简化为拒绝（强制 HTTPS CONNECT），避免半吊子转发
            writer.write(b"HTTP/1.1 501 Use HTTPS CONNECT\r\n\r\n")
            await writer.drain()
        except Exception as exc:  # noqa: BLE001
            _log.warning("sandbox.egress.error %s", exc)
        finally:
            try:
                writer.close()
            except Exception:  # noqa: BLE001
                pass


async def _pipe(src: asyncio.StreamReader, dst: asyncio.StreamWriter) -> None:
    try:
        while True:
            data = await src.read(65536)
            if not data:
                break
            dst.write(data)
            await dst.drain()
    except Exception:  # noqa: BLE001
        pass
    finally:
        try:
            dst.close()
        except Exception:  # noqa: BLE001
            pass


_proxy: EgressProxy | None = None


async def ensure_egress_proxy(port: int, allowlist: Iterable[str]) -> EgressProxy:
    """启动或复用代理；复用时合并 allowlist，避免后发会话丢域名。"""
    global _proxy
    if _proxy is None:
        _proxy = EgressProxy(port, allowlist)
        await _proxy.start()
    else:
        _proxy._allow |= {a.strip().lower().lstrip(".") for a in allowlist if a.strip()}
    return _proxy