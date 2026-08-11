"""api 包 — FastAPI HTTP 适配层

本包职责
========
把 ``main.AgentApplication``（CLI / 业务核心）暴露为 REST + SSE 接口，
供前端（如 Vite ``localhost:5173``）或其它 HTTP 客户端调用。

架构位置
========
::

    前端 / HTTP 客户端
           │
           ▼
    api.server  (FastAPI app, CORS, lifespan)
           │
           ├── api.routes.*   路由：chat / sessions / knowledge
           ├── api.schemas    请求/响应 Pydantic 模型
           └── api.deps       进程内单例 AgentApplication 的注入与生命周期
           │
           ▼
    main.AgentApplication  →  agents / rag / memory / safety / llm

设计原则
========
- **薄适配层**：路由只做参数校验、模式分发、错误映射；业务逻辑留在 ``AgentApplication``。
- **依赖注入**：通过 ``Depends(get_agent_app)`` 取全局实例，避免每个请求 ``new`` 一整套 LLM/向量库。
- **启动期初始化**：在 FastAPI ``lifespan`` 里 ``await init_session_store()``，保证会话后端就绪后再接流量。

启动方式（在项目根目录执行）::

    uvicorn api.server:app --reload --host 0.0.0.0 --port 8000

或::

    python -m uvicorn api.server:app --reload --port 8000
"""
