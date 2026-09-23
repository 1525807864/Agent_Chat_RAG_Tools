"""混合检索 RAG 用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from langchain_core.output_parsers import StrOutputParser

from application.tenancy import tenant_bm25_path
from billing.usage import LEDGER
from domain.run import RunResult
from observability.tracing import trace
from rag.evidence import INSUFFICIENT_ANSWER, has_enough_evidence
from rag.hybrid_retriever import HybridRetriever
from rag.query_router import RouteDecision, route_query
from rag.rag_chain import RAG_PROMPT, format_docs
from rag.sparse_bm25 import BM25SparseIndex
from shared.errors import sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class RagUseCase:
    """稠密 + BM25 混合检索问答。"""

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
        answer, sources = await self._run(
            message,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return RunResult(
            answer=answer,
            meta={"capability": "rag", "sources": sources},
        )

    async def _run(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        app = self._app
        blocked = await app.security.guard(question, rate_limit=True)
        if blocked:
            return blocked, []

        llm = app._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        store = app._vector_store_for_tenant(tenant_id)
        bm25 = BM25SparseIndex.load(tenant_bm25_path(app.project_root, tenant_id))

        if app.settings.hybrid_use_router:
            decision = route_query(question)
        else:
            decision = RouteDecision("hybrid", "router 关闭，强制 hybrid")

        if not app.settings.hybrid_retrieval_enabled:
            decision = RouteDecision("dense", "HYBRID_RETRIEVAL_ENABLED=false")

        retriever = HybridRetriever(
            store,
            bm25,
            top_k=app.settings.retrieval_top_k,
            fetch_k=app.settings.hybrid_fetch_k,
            rrf_k=app.settings.hybrid_rrf_k,
            mode=decision.strategy,
        )

        sources: list[dict] = []
        docs: list = []
        try:
            hits = retriever.retrieve(question)
            docs = [h.doc for h in hits]
            sources = app._docs_to_sources(docs)
            for i, h in enumerate(hits):
                if i < len(sources):
                    sources[i]["rrf_score"] = round(h.rrf_score, 6)
                    sources[i]["dense_rank"] = h.dense_rank
                    sources[i]["sparse_rank"] = h.sparse_rank
                    sources[i]["route"] = decision.strategy
        except Exception as e:
            app.logger.error("混合检索失败，回退纯向量: %s", e)
            try:
                docs = store.similarity_search(question, k=app.settings.retrieval_top_k)
            except Exception as e2:
                return f"问答出错: {sanitize_exception_message(e2)}", []
            sources = app._docs_to_sources(docs)

        if not has_enough_evidence(docs):
            return INSUFFICIENT_ANSWER, sources
        context = format_docs(docs)

        try:
            chain = RAG_PROMPT | llm | StrOutputParser()
            result = chain.invoke({"context": context, "question": question})
            answer = result if isinstance(result, str) else str(result)
            LEDGER.add(tenant_id, requests=1)
            trace(
                "rag_ask_hybrid",
                tenant_id=tenant_id,
                hits=len(sources),
                route=decision.strategy,
                reason=decision.reason,
            )
            return answer, sources
        except Exception as e:
            app.logger.error("RAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", sources
