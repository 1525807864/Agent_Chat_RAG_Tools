"""应用服务集合。"""

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
