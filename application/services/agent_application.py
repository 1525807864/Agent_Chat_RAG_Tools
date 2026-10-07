"""AgentApplication — 应用服务门面（组装依赖 + 兼容旧 ask_*）。

能力在 ``use_cases``；HTTP 走 ``orchestrator``。本文件只做接线。
旧 ``ask_*`` 签名见 ``ask_compat.AskCompatMixin``。
"""

from __future__ import annotations

from typing import Any

from agents.tools_registry import create_default_registry
from application.llm_factory import resolve_request_llm
from application.memory_bootstrap import bootstrap_session_memory
from application.security_policy import SecurityPolicy
from application.services.ask_compat import AskCompatMixin
from application.skills_runtime import SkillsRuntime
from application.tenant_resources import TenantResources, docs_to_sources
from application.tools import ToolGateway
from application.use_cases.bundle import UseCaseBundle
from billing.factory import create_usage_ledger
from config.settings import get_settings
from infrastructure.llm.deepseek import DeepSeekChatModel
from memory.facade import MemoryFacade
from orchestration.pipeline import ChatOrchestrator
from rag.document_loader import DocumentLoader
from rag.knowledge_graph import GraphRAGRetriever, KnowledgeGraph
from rag.vector_store import VectorStoreManager
from safety.content_filter import ContentFilter
from safety.rate_limiter import AsyncRateLimiter
from shared.path_security import get_project_root
from utils.logger import setup_logger


class AgentApplication(AskCompatMixin):
    """CLI / FastAPI 共用门面：依赖组装 + UseCase / Orchestrator 委托。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = setup_logger(level=self.settings.log_level)
        self.project_root = get_project_root()

        self.llm = DeepSeekChatModel(
            model_name=self.settings.model_name,
            temperature=self.settings.model_temperature,
            max_tokens=self.settings.model_max_tokens,
            api_key=self.settings.deepseek_api_key or "",
            api_base=self.settings.deepseek_api_base or "",
        )

        self.session_store = None
        self.memory: MemoryFacade | None = None

        self.vector_store = VectorStoreManager(
            embedding_model=self.settings.embedding_model,
            persist_dir=self.settings.vector_db_path,
        )
        self.knowledge_graph = KnowledgeGraph(
            persist_path=self.settings.knowledge_graph_path,
            auto_load=True,
        )
        self.graph_rag_retriever = GraphRAGRetriever(
            self.vector_store,
            self.knowledge_graph,
            depth=self.settings.graph_rag_depth,
            top_k=self.settings.retrieval_top_k,
        )

        self.tool_registry = create_default_registry(
            allowed_roots=self.settings.allowed_data_roots,
            project_root=self.project_root,
            enable_execute_python=self.settings.enable_execute_python,
        )
        self.tool_gateway = ToolGateway(
            self.tool_registry,
            mcp_servers_json=self.settings.mcp_servers_json,
            active_tool_discovery=bool(self.settings.active_tool_discovery),
            active_tool_base=self.settings.active_tool_base or "",
            active_tool_top_k=int(self.settings.active_tool_top_k),
            logger=self.logger,
        )

        self.tenants = TenantResources(self.settings, self.project_root)
        self.skills = SkillsRuntime(self.project_root, self.logger)
        self.usage_ledger = create_usage_ledger(self.settings)

        self.rate_limiter = AsyncRateLimiter(
            max_requests=self.settings.rate_limit_requests,
        )
        self.content_filter = ContentFilter(
            blocked_keywords=self.settings.blocked_keywords,
        )
        self.security = SecurityPolicy(self.content_filter, self.rate_limiter)
        self.doc_loader = DocumentLoader(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )

        self.use_cases = UseCaseBundle(self)
        self.orchestrator = ChatOrchestrator(self)

        self.logger.info(
            "Agent 应用程序初始化完成 (graph_nodes=%s, graph_path=%s)",
            self.knowledge_graph.graph.number_of_nodes(),
            self.settings.knowledge_graph_path,
        )

    def _resolve_llm(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
    ) -> DeepSeekChatModel:
        return resolve_request_llm(
            self.settings,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            temperature=temperature,
        )

    def intent_guard_for(
        self,
        *,
        session_id: str,
        tenant_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        event_sink: Any = None,
    ):
        """构造 IntentGuardService；关闭 / 失败时返回 None（fail-open）。"""
        if not self.settings.intent_guard_enabled:
            return None
        try:
            from intent.service import IntentGuardService

            check_llm = self._resolve_llm(
                api_key=api_key,
                api_base=api_base,
                model_name=(
                    (self.settings.intent_check_model_name or "").strip()
                    or model_name
                ),
                temperature=0.0,
            )
            return IntentGuardService(
                settings=self.settings,
                llm=check_llm,
                memory=self.memory,
                session_id=session_id,
                tenant_id=tenant_id,
                event_sink=event_sink,
                logger=self.logger,
            )
        except Exception as e:  # noqa: BLE001
            self.logger.warning("意图守卫初始化失败: %s", e)
            return None

    async def _ensure_skills(self):
        return await self.skills.ensure()

    async def _resolve_skill_for_turn(
        self,
        user_input: str,
        session_id: str,
        *,
        active_file: str | None = None,
    ):
        return await self.skills.resolve_for_turn(
            user_input, session_id, active_file=active_file
        )

    def _vector_store_for_tenant(self, tenant_id: str) -> VectorStoreManager:
        return self.tenants.vector_store(tenant_id)

    def _graph_for_tenant(self, tenant_id: str) -> KnowledgeGraph:
        return self.tenants.graph(tenant_id)

    @staticmethod
    def _docs_to_sources(docs: list) -> list[dict]:
        return docs_to_sources(docs)

    async def init_session_store(self) -> None:
        self.session_store, self.memory = await bootstrap_session_memory(
            settings=self.settings,
            project_root=self.project_root,
            llm=self.llm,
        )

    @staticmethod
    def _build_files_prefix(files: list | None) -> str:
        from application.prompts.files import build_files_prefix

        return build_files_prefix(files)
