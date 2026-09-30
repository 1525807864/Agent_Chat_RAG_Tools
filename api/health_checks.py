"""readiness 依赖探测。

原则
====
1. 快失败，避免探针拖死自己
2. 关键失败 → 整体 not ready；非关键仅告警
3. 不在这里真调大模型
"""

from __future__ import annotations

import time
from typing import Callable

from api.deps import get_agent_app
from api.health_state import DependencyCheck
from config.settings import get_settings


def _timed(name: str, fn: Callable[[], None]) -> DependencyCheck:
    """包一层计时；异常 → ok=False。"""
    t0 = time.perf_counter()
    try:
        fn()
        return DependencyCheck(
            name=name,
            ok=True,
            detail="ok",
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )
    except Exception as e:  # noqa: BLE001
        return DependencyCheck(
            name=name,
            ok=False,
            detail=str(e)[:300],
            latency_ms=round((time.perf_counter() - t0) * 1000, 2),
        )


def check_agent_app() -> DependencyCheck:
    """AgentApplication 单例是否已由 lifespan 初始化。"""

    def _run() -> None:
        app = get_agent_app()
        if app.session_store is None:
            raise RuntimeError("session_store 尚未就绪")

    return _timed("agent_app", _run)


async def run_readiness_checks_async() -> list[DependencyCheck]:
    """供 GET /health/ready 与 lifespan 末尾复用。"""
    settings = get_settings()
    checks: list[DependencyCheck] = []

    # 关键：业务单例
    checks.append(check_agent_app())

    # 关键：会话存储轻探
    t0 = time.perf_counter()
    try:
        app = get_agent_app()
        await app.session_store.list_sessions()
        checks.append(
            DependencyCheck(
                name="session_store",
                ok=True,
                detail=f"backend={settings.memory_backend}",
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
        )
    except Exception as e:  # noqa: BLE001
        checks.append(
            DependencyCheck(
                name="session_store",
                ok=False,
                detail=str(e)[:300],
                latency_ms=round((time.perf_counter() - t0) * 1000, 2),
            )
        )

    # 非关键：是否配置了 API Key（不泄露长度/内容）
    key = (settings.deepseek_api_key or "").strip()
    checks.append(
        DependencyCheck(
            name="llm_api_key_configured",
            ok=bool(key),
            detail="configured" if key else "missing DEEPSEEK_API_KEY",
        )
    )
    return checks


def critical_ok(checks: list[DependencyCheck]) -> bool:
    """只有名单内的依赖失败才让整体 not ready。"""
    critical_names = {"agent_app", "session_store"}
    for c in checks:
        if c.name in critical_names and not c.ok:
            return False
    return True
