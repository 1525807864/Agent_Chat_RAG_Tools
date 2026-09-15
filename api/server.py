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
    uvicorn api.server:app --reload --port 8000

然后打开 http://127.0.0.1:8000/docs 查看交互式 API 文档。
"""

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.auth.security_guard import assert_auth_config
from api.auth.user_store import init_user_store
from api.deps import init_agent_app, shutdown_agent_app
from api.exception_handlers import register_exception_handlers
from api.middleware import ApiRateLimitMiddleware, SecurityHeadersMiddleware
from api.schemas import HealthResponse
from api.routes import chat as chat_routes
from api.routes import sessions as sessions_routes
from api.routes import knowledge as knowledge_routes
from api.routes import auth_debug as auth_debug_routes
from api.routes import auth_login as auth_login_routes
from api.routes import billing as billing_routes
from config.settings import get_settings
from safety.http_rate_limit import init_http_rate_limiter, shutdown_http_rate_limiter


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """FastAPI 生命周期钩子：启动时初始化业务单例，关闭时清理引用。

    为何用 lifespan 而不是 ``@app.on_event("startup")``
    --------------------------------------------------
    FastAPI / Starlette 推荐 lifespan 上下文管理器写法，可同时覆盖 startup 与 shutdown，
    且与 ASGI 规范一致；旧版 ``on_event`` 已不推荐新项目使用。

    行为
    ----
    - yield 之前：``await init_agent_app()``，失败则服务起不来（避免「假健康」接请求）
    - yield 之后：``await shutdown_agent_app()``，释放模块级单例引用
    """
    settings = get_settings()
    assert_auth_config(settings)
    init_user_store()
    await init_http_rate_limiter()
    await init_agent_app()
    try:
        yield
    finally:
        await shutdown_http_rate_limiter()
        # 无论正常关闭还是异常退出路径，都尽量清理单例引用。
        await shutdown_agent_app()


# ---------------------------------------------------------------------------
# 创建应用实例
# ---------------------------------------------------------------------------
# title/version 会出现在 OpenAPI 文档顶部，便于前后端对齐环境。
_settings = get_settings()
app = FastAPI(
    title="LangChain Demo Agent API",
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

# 后添加的中间件先执行：限流 → 安全头 → CORS
app.add_middleware(ApiRateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

_hosts = [h.strip() for h in _settings.allowed_hosts.split(",") if h.strip()]
if _hosts and "*" not in _hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_hosts)

# CORS：白名单来自 CORS_ORIGINS（逗号分隔），生产改为你的 https 域名。
app.add_middleware(
    CORSMiddleware,
    allow_origins=_settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-Id"],
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


@app.get("/health", response_model=HealthResponse, tags=["system"])
async def health() -> HealthResponse:
    """健康检查：不依赖 AgentApplication，进程起来即可 200。

    用途
    ----
    - 负载均衡 / Docker HEALTHCHECK 探活
    - 前端启动时确认 API 地址是否正确
    - ``modes`` 字段给前端做模式选择器的权威列表，避免前后端枚举漂移

    注意
    ----
    本接口**不**证明 LLM Key、向量库或 Redis 已就绪；那些应在调用业务接口时
    或单独的 readiness 探针中验证。当前为保持简单，只做 liveness。
    """
    return HealthResponse(
        status="ok",
        modes=["chat", "rag", "graph-rag", "agent", "multi"],
    )


# 允许 ``python api/server.py`` 或 ``python -m api.server`` 直接拉起开发服务器。
# 生产环境更推荐外部用 uvicorn/gunicorn 管理进程，而不是本入口。
if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.server:app", host="127.0.0.1", port=8000, reload=True)
