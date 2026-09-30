"""GraphRAG 用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from billing.turn_helper import empty_turn, merge_message, safe_record_turn
from domain.run import RunResult
from observability.tracing import trace
from rag.knowledge_graph import GraphRAGRetriever
from rag.rag_chain import create_graph_rag_chain
from shared.errors import sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class GraphRagUseCase:
    """向量 + 知识图谱增强问答。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str,
        *,
        tenant_id: str = "default",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> RunResult:
        answer, sources, usage_meta = await self._run(
            message,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return RunResult(
            answer=answer,
            meta={"capability": "graph-rag", "sources": sources, **usage_meta},
        )

    async def _run(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict], dict]:
        app = self._app
        blocked = await app.security.guard(question, rate_limit=False)
        if blocked:
            return blocked, [], {}

        llm = app._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        store = app._vector_store_for_tenant(tenant_id)
        graph = app._graph_for_tenant(tenant_id)
        retriever = GraphRAGRetriever(
            store,
            graph,
            depth=app.settings.graph_rag_depth,
            top_k=app.settings.retrieval_top_k,
        )

        try:
            docs = store.similarity_search(question, k=app.settings.retrieval_top_k)
            sources = app._docs_to_sources(docs)
        except Exception:
            sources = []

        chain = create_graph_rag_chain(
            llm,
            retriever,
            top_k=app.settings.retrieval_top_k,
        )
        try:
            # chain 返回 AIMessage（已去掉 StrOutputParser）
            ai_msg = chain.invoke({"question": question})
            raw = getattr(ai_msg, "content", ai_msg)
            answer = raw if isinstance(raw, str) else str(raw or "")
            model_str = str(getattr(llm, "model_name", None) or model_name or "")
            turn = merge_message(empty_turn(model=model_str), ai_msg, model=model_str)
            usage_meta = safe_record_turn(app, tenant_id, turn, model=model_str)
            trace("graph_rag_ask", tenant_id=tenant_id, hits=len(sources))
            return answer, sources, usage_meta
        except Exception as e:
            app.logger.error("GraphRAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", sources, {}
