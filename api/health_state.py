"""进程级「启动就绪」状态机。

约定
====
- liveness 失败 → 重启容器
- readiness 失败 → 摘流量，不重启
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    """UTC ISO8601，带 Z 后缀，避免 isoformat(format) 误用。"""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class DependencyCheck:
    """单个依赖的探测结果（出现在 /health/ready 的 checks 里）。"""

    name: str
    ok: bool
    detail: str = ""
    latency_ms: float | None = None


@dataclass
class HealthState:
    """进程内唯一健康状态（不要做成每请求新建）。"""

    ready: bool = False
    startup_error: str | None = None
    last_checks: list[DependencyCheck] = field(default_factory=list)
    started_at: str | None = None
    ready_at: str | None = None

    def mark_starting(self) -> None:
        """lifespan 入口：开始初始化。"""
        self.ready = False
        self.startup_error = None
        self.started_at = _now_iso()
        self.ready_at = None
        self.last_checks = []

    def mark_ready(self, checks: list[DependencyCheck] | None = None) -> None:
        """关键初始化成功，可接流量。"""
        self.ready = True
        self.startup_error = None
        self.ready_at = _now_iso()
        if checks is not None:
            self.last_checks = checks

    def mark_failed(
        self, error: str, checks: list[DependencyCheck] | None = None
    ) -> None:
        """启动失败：ready 保持 False，供探针返回 503。"""
        self.ready = False
        self.startup_error = error
        if checks is not None:
            self.last_checks = checks

    def mark_not_ready(self) -> None:
        """shutdown / 主动摘流。"""
        self.ready = False
        self.ready_at = None

    def snapshot(self) -> dict[str, Any]:
        """给 HTTP 响应组 JSON 用。"""
        return {
            "ready": self.ready,
            "startup_error": self.startup_error,
            "started_at": self.started_at,
            "ready_at": self.ready_at,
            "checks": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "detail": c.detail,
                    "latency_ms": c.latency_ms,
                }
                for c in self.last_checks
            ],
        }


# 进程级单例：lifespan 与 /health/* 路由共用
health_state = HealthState()
