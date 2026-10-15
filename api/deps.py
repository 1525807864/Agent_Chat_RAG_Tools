"""api.deps — FastAPI 依赖注入与 AgentApplication 进程级生命周期。

业务入口已迁至 ``application.services.agent_application.AgentApplication``；
``main.AgentApplication`` 仍为兼容再导出，二者为同一类。
"""

from typing import Optional

from application.services.agent_application import AgentApplication
from utils.logger import get_logger

_app: Optional[AgentApplication] = None
_log = get_logger("nexora.deps")


def get_agent_app() -> AgentApplication:
    """供 FastAPI ``Depends`` 使用的同步依赖函数。"""
    if _app is None:
        _log.error("get_agent_app: AgentApplication 尚未初始化")
        raise RuntimeError(
            "AgentApplication 未初始化（请确认 lifespan 已成功执行 init_agent_app）"
        )
    return _app


def is_agent_app_ready() -> bool:
    """不抛异常，给探针/中间件使用"""
    return _app is not None and _app.session_store is not None


async def init_agent_app() -> AgentApplication:
    """应用启动时初始化业务单例并就绪会话存储。"""
    global _app
    _log.info("开始初始化 AgentApplication…")
    _app = AgentApplication()
    await _app.init_session_store()
    _log.info(
        "AgentApplication 就绪 session_store=%s memory=%s",
        type(_app.session_store).__name__ if _app.session_store else None,
        type(_app.memory).__name__ if _app.memory else None,
    )
    return _app


async def shutdown_agent_app() -> None:
    """应用关闭时释放对业务单例的引用。"""
    global _app
    _log.info("释放 AgentApplication 单例")
    _app = None
