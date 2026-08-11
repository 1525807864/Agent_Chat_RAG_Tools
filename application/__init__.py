"""应用层：用例编排与应用服务门面。

对外主入口：``application.services.agent_application.AgentApplication``。
CLI（``main.py``）与 FastAPI（``api/``）均依赖本层，不直接拼装基础设施细节。
"""

from application.services.agent_application import AgentApplication

__all__ = ["AgentApplication"]
