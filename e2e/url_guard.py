"""校验用户给出的被测站点 URL，并检查生成脚本有没有偷跑到别的主机。"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

_ABS_URL = re.compile(r"https?://[^\s\"'`<>]+", re.IGNORECASE)
_LOCAL_NAMES = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}


class E2EUrlError(ValueError):
    """校验失败时抛给工具层，转成字符串返回给 Agent。"""


def _host_ips(host: str) -> list[ipaddress._BaseAddress]:
    """解析主机名到 IP；解析失败就当非法。"""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise E2EUrlError(f"无法解析主机: {host}") from exc
    ips = []
    for item in infos:
        ip_s = item[4][0]
        ips.append(ipaddress.ip_address(ip_s))
    if not ips:
        raise E2EUrlError(f"无法解析主机: {host}")
    return ips


def validate_base_url(raw: str, *, allow_local: bool) -> str:
    """把用户输入收成规范的 http(s) origin。"""
    text = (raw or "").strip()
    if not text:
        raise E2EUrlError("e2e_base_url 不能为空")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        raise E2EUrlError("只允许 http 或 https")
    if not parsed.hostname:
        raise E2EUrlError("缺少主机名")
    host = parsed.hostname.lower()
    if host in _LOCAL_NAMES and not allow_local:
        raise E2EUrlError("禁止测本机地址；本机调试请设 E2E_ALLOW_LOCAL=true")
    for ip in _host_ips(host):
        private = (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
        )
        if private and not allow_local:
            raise E2EUrlError(f"禁止访问内网/保留地址: {ip}")
    origin = f"{parsed.scheme}://{parsed.netloc}".rstrip("/")
    return origin


def start_path_from_url(raw: str) -> str:
    """取出用户 URL 的路径。登录页往往是 /v2/user/login，不能只打开 /。"""
    parsed = urlparse((raw or "").strip())
    path = parsed.path or "/"
    if len(path) > 1:
        path = path.rstrip("/")
    return path or "/"


def spec_urls_are_same_origin(spec_text: str, origin: str) -> None:
    """扫描 spec，出现的绝对 URL 必须和本轮 origin 同源。"""
    want = urlparse(origin)
    for m in _ABS_URL.finditer(spec_text or ""):
        found = urlparse(m.group(0))
        if found.scheme not in {"http", "https"}:
            raise E2EUrlError(f"脚本含非法协议: {m.group(0)}")
        if (found.scheme, found.hostname, found.port) != (
            want.scheme,
            want.hostname,
            want.port,
        ):
            raise E2EUrlError(
                f"脚本跳到了非本轮站点: {m.group(0)}（只允许 {origin}）"
            )
