"""api.deps — FastAPI 依赖注入与 AgentApplication 进程级生命周期。

业务入口已迁至 ``application.services.agent_application.AgentApplication``；
``main.AgentApplication`` 仍为兼容再导出，二者为同一类。
"""

from typing import Optional

from application.services.agent_application import AgentApplication

_app: Optional[AgentApplication] = None


def get_agent_app() -> AgentApplication:
    """供 FastAPI ``Depends`` 使用的同步依赖函数。"""
    if _app is None:
        raise RuntimeError(
            "AgentApplication 未初始化（请确认 lifespan 已成功执行 init_agent_app）"
        )
    return _app


async def init_agent_app() -> AgentApplication:
    """应用启动时初始化业务单例并就绪会话存储。"""
    global _app
    _app = AgentApplication()
    await _app.init_session_store()
    return _app


async def shutdown_agent_app() -> None:
    """应用关闭时释放对业务单例的引用。"""
    global _app
    _app = None
