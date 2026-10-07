"""结构化咨询用例。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from application.tenancy import (
    tenant_bm25_path,
    tenant_factor_records_path,
    tenant_factor_session_path,
)
from billing.turn_helper import safe_record_turn
from domain.run import RunResult
from rag.evidence import has_enough_evidence
from rag.hybrid_retriever import HybridRetriever
from rag.rag_chain import format_docs
from rag.sparse_bm25 import BM25SparseIndex
from rag.structured.consult import run_consult
from rag.structured.records import load_record
from infrastructure.db.consult_factors_store import (
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
        task_events=None,
    ) -> RunResult:
        answer, sources, usage_meta = await self._run(
            message,
            tenant_id=tenant_id,
            session_id=session_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            task_events=task_events,
        )
        return RunResult(
            answer=answer,
            meta={"capability": "consult", "sources": sources, **usage_meta},
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
        task_events=None,
    ) -> tuple[str, list[dict], dict]:
        app = self._app
        blocked = await app.security.guard(question, rate_limit=False)
        if blocked:
            return blocked, [], {}

        if app.memory is None:
            await app.init_session_store()
        guard = app.intent_guard_for(
            session_id=session_id,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            event_sink=task_events,
        )
        if guard is not None:
            try:
                await guard.ensure_anchor(user_input=question)
                await guard.pre_turn_check(user_input=question)
            except Exception as e:  # noqa: BLE001
                app.logger.warning("意图守卫回合前检查失败: %s", e)

        llm = app._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        records = load_record(tenant_factor_records_path(app.project_root, tenant_id))
        state_path = tenant_factor_session_path(
            app.project_root, tenant_id, session_id
        )
        factors = load_session_factors(
            tenant_id=tenant_id,
            session_id=session_id,
            file_path=state_path,
            suffix="",
        )

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
            answer, updated, turn = run_consult(
                llm=llm,
                user_message=question,
                factors=factors,
                records=records,
                retrieve_context=retrieve_context,
            )
        except Exception as e:
            app.logger.error("consult 失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", [], {}

        save_session_factors(
            tenant_id=tenant_id,
            session_id=session_id,
            file_path=state_path,
            factors=updated,
        )
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

        usage_meta: dict = {}
        # 有 LLM token 才记账；纯规则追问留给 orchestrator 兜底 requests=1
        if turn.tokens_in or turn.tokens_out:
            model_str = str(getattr(llm, "model_name", None) or model_name or "")
            usage_meta = safe_record_turn(app, tenant_id, turn, model=model_str)
        # 意图守卫收尾：完成度校验 + 按需追加未完成清单
        if guard is not None:
            answer, intent_meta = await guard.close_turn(
                user_input=question, answer=answer
            )
            usage_meta = {**usage_meta, **intent_meta}
        return answer, sources, usage_meta
