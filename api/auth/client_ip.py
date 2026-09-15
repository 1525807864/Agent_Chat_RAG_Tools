"""取客户端 IP；只有 TRUST_PROXY=true 时才信反向代理头。"""

from __future__ import annotations

from fastapi import Request

from config.settings import get_settings


def client_ip(request: Request) -> str:
    settings = get_settings()
    if settings.trust_proxy:
        real = (request.headers.get("x-real-ip") or "").strip()
        if real:
            return real.split()[0]
        forwarded = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
        if forwarded:
            return forwarded
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
