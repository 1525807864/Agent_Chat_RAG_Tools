"""应用层：用例编排与应用服务门面。

对外主入口：``application.services.agent_application.AgentApplication``。
CLI（``main.py``）与 FastAPI（``api/``）均依赖本层，不直接拼装基础设施细节。

注意：本包 ``__init__`` 不做急切导入，避免
``orchestration → application.routing → application → AgentApplication → orchestration``
循环依赖。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication as AgentApplication

__all__ = ["AgentApplication"]


def __getattr__(name: str) -> Any:
    if name == "AgentApplication":
        from application.services.agent_application import AgentApplication

        return AgentApplication
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
