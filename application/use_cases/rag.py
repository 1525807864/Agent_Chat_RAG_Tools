"""混合检索 RAG 用例。"""


from __future__ import annotations  # 延迟注解
from typing import TYPE_CHECKING, Optional  # 类型；Optional 兼容旧写法
# 删掉：from langchain_core.output_parsers import StrOutputParser
# 删掉：from billing.usage import LEDGER
from application.tenancy import tenant_bm25_path  # 租户 BM25 文件路径
from billing.turn_helper import empty_turn, merge_message, safe_record_turn  # 计量+记账
from domain.run import RunResult  # 统一返回结构
from observability.tracing import trace  # 结构化日志
from rag.evidence import INSUFFICIENT_ANSWER, has_enough_evidence  # 证据门控
from rag.hybrid_retriever import HybridRetriever  # 混合检索
from rag.query_router import RouteDecision, route_query  # 路由
from rag.rag_chain import RAG_PROMPT, format_docs  # Prompt + 格式化 docs
from rag.sparse_bm25 import BM25SparseIndex  # BM25 索引
from shared.errors import sanitize_exception_message  # 错误脱敏
if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication  # 仅类型检查


class RagUseCase:
    """稠密 + BM25 混合检索问答。"""

    def __init__(self, app: AgentApplication) -> None:
        self._app = app

    async def execute(
        self,
        message: str, #用户问题
        *,
        tenant_id: str = "default", #租户，记账key
        api_key: Optional[str] = None, #api key，可选
        api_base: Optional[str] = None, #api base，可选
        model_name: Optional[str] = None, #模型，记账meta
    ) -> RunResult:
        # _run现在多返回usage_meta（可能是{}）
        answer, sources, usage_meta = await self._run(
            message,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return RunResult( #usage_meta可能为{}，不影响前端
            answer=answer,
            meta={"capability": "rag", "sources": sources, **usage_meta},
        )

    async def _run(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict],dict]:
        app = self._app
        blocked = await app.security.guard(question, rate_limit=False)
        if blocked:
            return blocked, [], {}

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
                return f"问答出错: {sanitize_exception_message(e2)}", [], {}
            sources = app._docs_to_sources(docs)

        if not has_enough_evidence(docs):
            return INSUFFICIENT_ANSWER, sources, {}
        context = format_docs(docs) #把文档拼进prompt的context里面

        try:
            chain = RAG_PROMPT | llm 
            # 调用大模型，得到AIMessage
            ai_msg = chain.invoke({"context": context, "question": question})
            # 从消息取文本答案
            raw = getattr(ai_msg,"content",ai_msg)
            answer = raw if isinstance(raw,str) else str(raw or "")
            #模型名
            model_str = str(getattr(llm,"model_name",None) or model_name or "")
            #从空回合合并本条消息的token
            turn = merge_message(empty_turn(model=model_str),ai_msg,model=model_str)
            # 安全记录回合用量，返回前端meta
            usage_meta = safe_record_turn(app,tenant_id,turn,model=model_str)
            # 记录日志
            trace(
                "rag_ask_hybrid",
                tenant_id=tenant_id,
                hits=len(sources),
                route=decision.strategy,
                reason=decision.reason,
            )
            return answer, sources, usage_meta
        except Exception as e:
            app.logger.error("RAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", sources, {}
