"""结构化咨询用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from application.tenancy import (
    tenant_bm25_path,
    tenant_factor_records_path,
    tenant_factor_session_path,
)
from domain.run import RunResult
from rag.evidence import has_enough_evidence
from rag.hybrid_retriever import HybridRetriever
from rag.rag_chain import format_docs
from rag.sparse_bm25 import BM25SparseIndex
from rag.structured.consult import run_consult
from rag.structured.records import (
    load_record,
    load_session_factors,
    save_session_factors,
)
from shared.errors import sanitize_exception_message

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class ConsultUseCase:
    """因子补全 + 混合检索。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str,
        *,
        tenant_id: str = "default",
        session_id: str = "default",
        api_key: Optional[str] = None,
        api_base: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> RunResult:
        answer, sources = await self._run(
            message,
            tenant_id=tenant_id,
            session_id=session_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return RunResult(
            answer=answer,
            meta={"capability": "consult", "sources": sources},
        )

    async def _run(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        session_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        app = self._app
        blocked = await app.security.guard(question, rate_limit=True)
        if blocked:
            return blocked, []

        llm = app._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        records = load_record(tenant_factor_records_path(app.project_root, tenant_id))
        state_path = tenant_factor_session_path(
            app.project_root, tenant_id, session_id
        )
        factors = load_session_factors(state_path, suffix="")

        store = app._vector_store_for_tenant(tenant_id)
        bm25 = BM25SparseIndex.load(tenant_bm25_path(app.project_root, tenant_id))
        hybrid = HybridRetriever(
            store,
            bm25,
            top_k=app.settings.retrieval_top_k,
            fetch_k=app.settings.hybrid_fetch_k,
            rrf_k=app.settings.hybrid_rrf_k,
            mode="hybrid",
        )

        def retrieve_context(query: str) -> str:
            hits = hybrid.retrieve(query)
            found = [hit.doc for hit in hits]
            if not has_enough_evidence(found):
                return ""
            return format_docs(found)

        try:
            answer, updated = run_consult(
                llm=llm,
                user_message=question,
                factors=factors,
                records=records,
                retrieve_context=retrieve_context,
            )
        except Exception as e:
            app.logger.error("consult 失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", []

        save_session_factors(state_path, updated)
        sources = [
            {
                "doc_id": str(item.get("source") or "record"),
                "snippet": str(item.get("factors") or "")[:300],
                "score": None,
                "page": None,
                "metadata": {"kind": "factor_record"},
            }
            for item in records[:5]
        ]
        return answer, sources
