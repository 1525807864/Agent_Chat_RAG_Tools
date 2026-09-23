"""UseCase 集合：挂在 AgentApplication 上，供编排层与路由使用。"""

from __future__ import annotations

from typing import TYPE_CHECKING

from application.use_cases.agent import AgentUseCase
from application.use_cases.chat import ChatUseCase
from application.use_cases.consult import ConsultUseCase
from application.use_cases.graph_rag import GraphRagUseCase
from application.use_cases.knowledge import KnowledgeBuildUseCase
from application.use_cases.multi import MultiAgentUseCase
from application.use_cases.rag import RagUseCase
from application.use_cases.session import SessionUseCase

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class UseCaseBundle:
    """把各 UseCase 收成一组，避免散落在 AgentApplication 字段里。"""

    def __init__(self, app: AgentApplication) -> None:
        self.chat = ChatUseCase(app)
        self.rag = RagUseCase(app)
        self.consult = ConsultUseCase(app)
        self.graph_rag = GraphRagUseCase(app)
        self.agent = AgentUseCase(app)
        self.multi = MultiAgentUseCase(app)
        self.session = SessionUseCase(app)
        self.knowledge = KnowledgeBuildUseCase(app)
