"""api.server — FastAPI 应用入口（ASGI app）

本模块职责
==========
组装完整的 HTTP 服务：
- 创建 ``FastAPI`` 实例并挂载 lifespan（启停时初始化/销毁 ``AgentApplication``）
- 配置 CORS，允许本地前端开发源访问
- ``include_router`` 挂载 chat / sessions / knowledge 路由
- 提供 ``GET /health`` 探活接口

在架构中的位置
==============
本文件是 ``uvicorn api.server:app`` 的加载目标；不包含业务算法，
只做「协议层胶水」。业务一律委托
``application.services.agent_application.AgentApplication``。

与 CLI 的关系
==============
``python main.py`` 走终端交互；本模块走 HTTP。二者共用同一套
``AgentApplication`` 类，但运行时是不同进程、各自一份实例。

启动示例
========
在仓库根目录 ``d:\\LangChain_Demo`` 下::

    pip install -r api/requirements.txt   # 若尚未安装 FastAPI 栈
    pip install -r requirements.txt       # 业务依赖（langchain 等）
    uvicorn api.server:app --reload --port 8020

然后打开 http://127.0.0.1:8020/docs 查看交互式 API 文档。
"""
from api.routes import qa as qa_routes
from api.routes import sandbox as sandbox_routes
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.auth.security_guard import assert_auth_config
from api.auth.user_store import init_user_store
from api.deps import init_agent_app, shutdown_agent_app
from api.exception_handlers import register_exception_handlers
from fastapi import Response, status
from api.routes import ops as ops_routes  # 运维排障门面（Holmes）
from api.routes import ops_terminal as ops_terminal_routes  # 交互终端（ttyd）
from api.health_checks import critical_ok, run_readiness_checks_async
from api.health_state import DependencyCheck, health_state
from api.middleware import (
    ReadinessGateMiddleware,
    SecurityHeadersMiddleware,
)
from api.schemas import (
    HealthResponse,
    LiveHealthResponse,
    ReadyCheckItem,
    ReadyHealthResponse,
)
from api.routes import chat as chat_routes
from api.routes import sessions as sessions_routes
from api.routes import knowledge as knowledge_routes
from api.routes import auth_debug as auth_debug_routes
from api.routes import auth_login as auth_login_routes
from api.routes import billing as billing_routes
from api.routes import downloads as download_routes
from config.settings import get_settings
from safety.http_rate_limit import init_http_rate_limiter, shutdown_http_rate_limiter

SUPPORTED_MODES = ["chat", "rag", "graph-rag", "agent", "multi", "consult"]


def _to_ready_items(checks: list[DependencyCheck]) -> list[ReadyCheckItem]:
    return [
        ReadyCheckItem(
            name=c.name,
            ok=c.ok,
            detail=c.detail,
            latency_ms=c.latency_ms,
        )
        for c in checks
    ]


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """启动闭环：mark_starting → 初始化 → readiness → mark_ready/failed → yield → 清理。"""
    health_state.mark_starting()
    settings = get_settings()

    try:
        assert_auth_config(settings)
        try:
            from observability.langsmith_trace import configure_langsmith

            configure_langsmith(settings)
        except Exception:  # noqa: BLE001
            pass
        init_user_store()
        # P0–P2：若 MySQL 可达则幂等建表（本机无库时静默跳过）
        try:
            from infrastructure.db.schema import ensure_all_schemas

            ensure_all_schemas()
        except Exception:  # noqa: BLE001
            pass
        await init_http_rate_limiter()
        await init_agent_app()
        # reload / 重启后清理僵尸建库任务（防前端一直显示 10%）
        try:
            from application.jobs.kb_jobs import fail_stale_running_jobs

            fail_stale_running_jobs(max_age_seconds=60)
        except Exception:  # noqa: BLE001
            pass

        checks = await run_readiness_checks_async()
        if not critical_ok(checks):
            bad = [c.name for c in checks if not c.ok]
            health_state.mark_failed(
                error=f"critical checks failed: {bad}",
                checks=checks,
            )
        else:
            health_state.mark_ready(checks=checks)

        # 平台沙箱：恢复落盘会话 + 空闲回收
        import asyncio

        reaper_task: asyncio.Task | None = None
        ttyd_reaper_task: asyncio.Task | None = None
        try:
            from infrastructure.sandbox.reaper import sweep_and_reap_forever

            reaper_task = asyncio.create_task(
                sweep_and_reap_forever(), name="sandbox-reaper"
            )
        except Exception:  # noqa: BLE001
            reaper_task = None

        # Ops 交互终端：回收过期 / 已死的 ttyd 进程
        try:
            from application.ops.ttyd_manager import get_ttyd_manager

            async def _ttyd_reap_forever() -> None:
                while True:
                    try:
                        n = await get_ttyd_manager().reap_expired()
                        if n:
                            import logging

                            logging.getLogger("nexora.ops.ttyd").info(
                                "reaped %s terminals", n
                            )
                    except Exception:  # noqa: BLE001
                        import logging

                        logging.getLogger("nexora.ops.ttyd").exception(
                            "ttyd reap failed"
                        )
                    await asyncio.sleep(30)

            ttyd_reaper_task = asyncio.create_task(
                _ttyd_reap_forever(), name="ttyd-reaper"
            )
        except Exception:  # noqa: BLE001
            ttyd_reaper_task = None

        try:
            yield
        finally:
            for task in (ttyd_reaper_task, reaper_task):
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            health_state.mark_not_ready()
            await shutdown_http_rate_limiter()
            await shutdown_agent_app()
    except Exception as e:
        health_state.mark_failed(error=str(e))
        raise


# ---------------------------------------------------------------------------
# 创建应用实例
# ---------------------------------------------------------------------------
# title/version 会出现在 OpenAPI 文档顶部，便于前后端对齐环境。
_settings = get_settings()
app = FastAPI(
    title="LSP Agent API",
    description=(
        "将 application.AgentApplication 暴露为 HTTP 接口："
        "chat / rag / graph-rag / agent / multi，以及会话与知识库管理。"
    ),
    version="0.2.0",
    lifespan=lifespan,
    docs_url="/docs" if _settings.openapi_enabled else None,
    redoc_url="/redoc" if _settings.openapi_enabled else None,
    openapi_url="/openapi.json" if _settings.openapi_enabled else None,
)

register_exception_handlers(app)

# 后 add 的中间件更靠外：CORS → 安全头 → 就绪门闩 → 路由
# 全站 /api 限流已关闭；登录/注册限流见 api/routes/auth_login.py
app.add_middleware(ReadinessGateMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_hosts = [h.strip() for h in _settings.allowed_hosts.split(",") if h.strip()]
if _hosts and "*" not in _hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

# CORS：白名单来自 CORS_ORIGINS；本地常见 Origin 在非严格模式下自动并入，避免预检 400。
_cors_origins = list(_settings.cors_origin_list())
if not _settings.strict_production:
    for _o in (
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:5174",
        "http://localhost:5174",
    ):
        if _o not in _cors_origins:
            _cors_origins.append(_o)

# allow_headers=["*"]：浏览器预检常带 authorization/content-type 等，写死列表易 400。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# 正式登录始终挂载
app.include_router(auth_login_routes.router)
# 调试发 Token：仅 AUTH_DEBUG_ENABLED=true 时挂载
if _settings.auth_debug_enabled:
    app.include_router(auth_debug_routes.router)
app.include_router(chat_routes.router)
app.include_router(sessions_routes.router)
app.include_router(knowledge_routes.router)
app.include_router(billing_routes.router)
app.include_router(download_routes.router)
app.include_router(qa_routes.router)
app.include_router(sandbox_routes.router)
app.include_router(ops_routes.router)
app.include_router(ops_terminal_routes.router)
@app.get("/health/live", response_model=LiveHealthResponse, tags=["system"])
@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health_live() -> LiveHealthResponse:
    """liveness：进程存活即可 200。Docker/K8s livenessProbe 打这里。"""
    return LiveHealthResponse(status="ok", modes=SUPPORTED_MODES)


@app.get("/health/ready", response_model=ReadyHealthResponse, tags=["system"])
async def health_ready(response: Response) -> ReadyHealthResponse:
    """readiness：可接流量才 200，否则 503。"""
    if not health_state.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        snap = health_state.snapshot()
        return ReadyHealthResponse(
            status="not_ready",
            ready=False,
            startup_error=snap["startup_error"],
            started_at=snap["started_at"],
            ready_at=snap["ready_at"],
            checks=_to_ready_items(health_state.last_checks),
            modes=SUPPORTED_MODES,
        )

    checks = await run_readiness_checks_async()
    health_state.last_checks = checks
    if not critical_ok(checks):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return ReadyHealthResponse(
            status="not_ready",
            ready=False,
            startup_error="runtime dependency check failed",
            started_at=health_state.started_at,
            ready_at=health_state.ready_at,
            checks=_to_ready_items(checks),
            modes=SUPPORTED_MODES,
        )

    return ReadyHealthResponse(
        status="ready",
        ready=True,
        startup_error=None,
        started_at=health_state.started_at,
        ready_at=health_state.ready_at,
        checks=_to_ready_items(checks),
        modes=SUPPORTED_MODES,
    )


# 允许 ``python api/server.py`` 或 ``python -m api.server`` 直接拉起开发服务器。
# 生产环境更推荐外部用 uvicorn/gunicorn 管理进程，而不是本入口。
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app",debug=True ,host="127.0.0.1", port=8020, reload=True)
