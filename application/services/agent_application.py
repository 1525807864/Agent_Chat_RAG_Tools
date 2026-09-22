"""AgentApplication — 应用服务门面（原 main.AgentApplication）。

职责
====
组装 LLM、会话存储、向量库、知识图谱、工具、多 Agent 编排与安全策略，
对外提供 ``ask_*`` / ``build_knowledge_base`` / 会话查询等用例方法。

调用方
======
- CLI：``interfaces.cli`` / ``main.py``
- HTTP：``api.deps`` 在 FastAPI lifespan 中单例化

安全
====
所有问答路径经 ``SecurityPolicy``（内容过滤 + 限流）；
``doc_dir`` / 工具读文件受 ``shared.path_security`` 白名单约束。
"""

from __future__ import annotations
from rag.evidence import has_enough_evidence, INSUFFICIENT_ANSWER
import asyncio
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.react_agent import RESEARCHER_SYSTEM_PROMPT, ReActAgent
from agents.tools_registry import create_default_registry, make_workspace_tools
from application.security_policy import SecurityPolicy
from config.settings import get_settings
from infrastructure.llm.deepseek import DeepSeekChatModel
from memory.facade import MemoryFacade
from memory.session_store import create_session_store
from rag.document_loader import DocumentLoader
from rag.knowledge_graph import GraphRAGRetriever, KnowledgeGraph
from rag.rag_chain import create_graph_rag_chain
from rag.vector_store import VectorStoreManager
from safety.content_filter import ContentFilter
from safety.rate_limiter import AsyncRateLimiter
from shared.errors import AppError, ErrorCode, sanitize_exception_message
from shared.path_security import PathSecurityError, get_project_root, resolve_safe_path
from utils.logger import setup_logger


class AgentApplication:
    """完整 Agent 应用服务 — CLI 与 FastAPI 共用业务门面。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.logger = setup_logger(level=self.settings.log_level)
        self.project_root = get_project_root()

        # 启动默认模型：凭证来自 Settings/.env，运行时可被请求级覆盖
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

        # 知识图谱：启动时从 JSON 恢复（若存在）
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

        # 租户级向量库缓存（P1）
        self._tenant_vector_stores: dict[str, VectorStoreManager] = {}
        self._tenant_graphs: dict[str, KnowledgeGraph] = {}

        self.rate_limiter = AsyncRateLimiter(
            max_requests=self.settings.rate_limit_requests,
        )
        self.content_filter = ContentFilter(
            blocked_keywords=self.settings.blocked_keywords,
        )
        self.security = SecurityPolicy(self.content_filter, self.rate_limiter)

        # Skills：懒加载缓存（/explain 等 slash 命令）；见 _ensure_skills / ask_chat
        self._skills = None

        self.doc_loader = DocumentLoader(
            chunk_size=self.settings.chunk_size,
            chunk_overlap=self.settings.chunk_overlap,
        )

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
        """根据「本轮请求」解析出要使用的 ChatModel。

        优先级（从高到低）：
        1. 本次参数（前端 Settings / Skill frontmatter 传来的）
        2. Settings / .env 里的默认值

        为什么每次可能 new 一个模型对象？
        - AgentApplication 是进程单例，不能把用户 A 的 Key 写进 self.llm 污染用户 B
        - 请求级覆盖最安全、最好理解

        注意：不要 logger.info(api_key)！空字符串视为「未提供」，继续回退。
        """
        # strip：避免用户复制 Key 时带了首尾空格
        key = (api_key or "").strip() or (self.settings.deepseek_api_key or "").strip()
        base = (api_base or "").strip() or (self.settings.deepseek_api_base or "").strip()
        model = (model_name or "").strip() or (self.settings.model_name or "").strip()
        temp = (
            self.settings.model_temperature
            if temperature is None
            else float(temperature)
        )

        if not key:
            # 用 AppError，接口层映射成 HTTP 状态码，前端能直接展示这句话
            raise AppError(
                ErrorCode.UNAUTHORIZED,
                "请先在设置中填写 API Key，或在服务端 .env 配置 DEEPSEEK_API_KEY",
                http_status=401,
            )

        if not base:
            # Base 一般有默认值；若被清空则给明确错误，避免 OpenAI 客户端指向错误主机
            raise AppError(
                ErrorCode.VALIDATION,
                "请填写 API Base（例如 https://api.deepseek.com/v1）",
                http_status=400,
            )

        return DeepSeekChatModel(
            model_name=model,
            temperature=temp,
            max_tokens=self.settings.model_max_tokens,
            api_key=key,
            api_base=base,
        )

    async def _ensure_skills(self):
        """懒加载项目内 Skills（data/skills + .claude/skills），并缓存到 self._skills。

        刻意不扫描 ~/.claude/skills，避免把本机 Claude Code 教学技能混进本 Demo。
        """
        if self._skills is not None:
            return self._skills

        from pathlib import Path

        from skills.load_skills import discover_skills

        demo_dir = self.project_root / "data" / "skills"
        project_claude = self.project_root / ".claude" / "skills"
        project_dirs = [project_claude] if project_claude.is_dir() else []

        self._skills = await discover_skills(
            cwd=str(self.project_root),
            # 用空目录覆盖 user/policy，只保留项目内技能
            user_skills_dir=Path("__skills_user_disabled__"),
            policy_skills_dir=Path("__skills_policy_disabled__"),
            project_skills_dirs=project_dirs,
            demo_skills_dir=demo_dir if demo_dir.is_dir() else None,
            logger=lambda m: self.logger.info("[skills] %s", m),
            enable_shell=False,
        )
        self.logger.info(
            "Skills 已加载: %s",
            [c.name for c in self._skills] if self._skills else [],
        )
        return self._skills

    async def _resolve_skill_for_turn(
        self,
        user_input: str,
        session_id: str,
        *,
        active_file: str | None = None,
    ) -> tuple[str, str, str, object | None, float | None, str | None]:
        """解析本轮是否触发 slash Skill。

        返回:
            (effective_input, skill_system_extra, memory_session_id,
             resolved_or_none, temperature_override, model_override)

        未命中时 effective_input==user_input，skill_system_extra==""。
        """
        from skills.integrate_hooks import build_runtime_plan, resolve_and_build_skill_prefix
        from skills.types import MalformedCommandError

        skills = await self._ensure_skills()
        try:
            prefix, effective_q, resolved = await resolve_and_build_skill_prefix(
                user_input,
                skills,
                cwd=str(self.project_root),
                session_id=session_id,
                active_file=active_file,
            )
        except MalformedCommandError as e:
            # 权限拒绝等：冒泡成可读错误，由 ask_* 直接返回
            raise AppError(
                ErrorCode.VALIDATION,
                f"技能执行失败: {e}",
                http_status=400,
            ) from e

        if resolved is None:
            return user_input, "", session_id, None, None, None

        plan = build_runtime_plan(resolved.command, base_session_id=session_id)
        skill_extra = ""
        if prefix.strip():
            skill_extra = (
                f"\n\n# Active Skill: /{resolved.command.name}\n"
                f"请严格遵循下列技能说明完成用户请求：\n\n{prefix.strip()}\n"
            )
        self.logger.info(
            "Skill 激活: /%s args=%s session=%s",
            resolved.command.name,
            resolved.args,
            plan.session_id,
        )
        return (
            effective_q,
            skill_extra,
            plan.session_id,
            resolved,
            plan.temperature,
            plan.model_name,
        )


    def _vector_store_for_tenant(self, tenant_id: str) -> VectorStoreManager:
        """按租户返回（并缓存）向量库管理器。"""
        from application.tenancy import sanitize_tenant_id, tenant_vector_dir

        tid = sanitize_tenant_id(tenant_id)
        if tid not in self._tenant_vector_stores:
            persist = tenant_vector_dir(self.project_root, tid)
            self._tenant_vector_stores[tid] = VectorStoreManager(
                embedding_model=self.settings.embedding_model,
                persist_dir=str(persist),
            )
        return self._tenant_vector_stores[tid]

    def _graph_for_tenant(self, tenant_id: str) -> KnowledgeGraph:
        """按租户返回（并缓存）知识图谱。"""
        from application.tenancy import sanitize_tenant_id, tenant_graph_path

        tid = sanitize_tenant_id(tenant_id)
        if tid not in self._tenant_graphs:
            path = tenant_graph_path(self.project_root, tid)
            self._tenant_graphs[tid] = KnowledgeGraph(
                persist_path=str(path),
                auto_load=True,
            )
        return self._tenant_graphs[tid]

    @staticmethod
    def _docs_to_sources(docs: list) -> list[dict]:
        sources: list[dict] = []
        for d in docs:
            meta = dict(getattr(d, "metadata", None) or {})
            content = getattr(d, "page_content", "") or ""
            sources.append(
                {
                    "doc_id": str(
                        meta.get("source")
                        or meta.get("file_path")
                        or meta.get("filename")
                        or "unknown"
                    ),
                    "snippet": content[:300],
                    "score": meta.get("score"),
                    "page": meta.get("page"),
                    "metadata": meta,
                }
            )
        return sources

    async def init_session_store(self) -> None:
        """按 Settings.memory_backend 创建会话存储。"""
        backend = self.settings.memory_backend
        kwargs: dict = {}
        if backend == "redis":
            kwargs["redis_url"] = self.settings.redis_url
            kwargs["ttl_seconds"] = self.settings.memory_ttl_seconds
        elif backend == "sqlite":
            kwargs["db_path"] = self.settings.sqlite_db_path
        self.session_store = await create_session_store(backend=backend, **kwargs)

        mem_root = Path(self.settings.memdir_path)
        if not mem_root.is_absolute():
            mem_root = (self.project_root / mem_root).resolve()

        self.memory = MemoryFacade(
            session_store=self.session_store,
            llm=self.llm,
            project_root=self.project_root,
            window_size=self.settings.memory_window_size,
            solip_enabled=self.settings.memory_solip_enabled,
            solip_top_k=self.settings.memory_solip_top_k,
            relevance_top_k=self.settings.memory_relevance_top_k,
            memdir_root=mem_root,
        )

    # ===== 知识库构建 =====
    def build_knowledge_base(self, doc_dir: str, tenant_id: str = "default") -> int:
        """从本地目录构建**租户**向量库，并抽取三元组写入租户图谱。

        ``doc_dir`` 必须落在 ``allowed_data_roots`` 内。
        """
        try:
            safe_dir = resolve_safe_path(
                doc_dir,
                allowed_roots=self.settings.allowed_data_roots,
                project_root=self.project_root,
                must_exist=True,
                expect_dir=True,
            )
        except PathSecurityError as e:
            raise AppError(
                ErrorCode.PATH_DENIED,
                "知识库目录不在允许范围内",
                http_status=400,
                internal=str(e),
            ) from e

        store = self._vector_store_for_tenant(tenant_id)
        graph = self._graph_for_tenant(tenant_id)

        self.logger.info("开始构建知识库: tenant=%s dir=%s", tenant_id, safe_dir)
        docs = self.doc_loader.load_directory(safe_dir)
        # 有文件没读进去就整次失败，避免只建进 Excel、PDF 被丢掉还显示成功
        load_errors = list(getattr(self.doc_loader, "load_errors", []))
        if load_errors:
            detail = "\n".join(load_errors)
            raise AppError(
                ErrorCode.VALIDATION,
                "有文件未能读入，建库已中止：\n" + detail,
                http_status=400,
                internal=detail,
            )

        if not docs:
            self.logger.warning("未找到任何文档")
            return 0

        count = store.add_documents(docs)
        self.logger.info("知识库构建完成, tenant=%s chunks=%s", tenant_id, count)

        # 同步构建 BM25 稀疏索引（与向量库同一批 docs）
        from application.tenancy import tenant_bm25_path
        from rag.sparse_bm25 import BM25SparseIndex

        bm25 = BM25SparseIndex()
        bm25.build(docs)
        bm25_path = tenant_bm25_path(self.project_root, tenant_id)
        try:
            bm25.save(bm25_path)
            self.logger.info("BM25 索引已保存: %s (n=%s)", bm25_path, bm25.size)
        except Exception as e:
            self.logger.warning("BM25 保存失败: %s", e)

        # 按源文件抽因子，不要对每个 chunk 都调模型
        from application.tenancy import tenant_factor_records_path
        from rag.structured.extract import extract_factors
        from rag.structured.records import save_record

        grouped: dict[str, list[str]] = {}
        suffix_of: dict[str, str] = {}
        for doc in docs:
            src = str((doc.metadata or {}).get("source") or "")
            grouped.setdefault(src, []).append(doc.page_content or "")
            suffix_of[src] = Path(src).suffix.lower()
        records = []
        for src, parts in grouped.items():
            preview = "\n".join(parts)[:6000]
            factors = extract_factors(self.llm, preview, suffix_of.get(src, ""))
            records.append(
                {"source": src, "suffix": suffix_of.get(src, ""), "factors": factors}
            )
        try:
            save_record(
                tenant_factor_records_path(self.project_root, tenant_id),
                records,
            )
            self.logger.info("因子记录已保存: %s 个源文件", len(records))
        except Exception as e:
            self.logger.warning("因子记录保存失败: %s", e)

        max_chars = self.settings.graph_extract_max_chars
        for doc in docs:
            graph.extract_triples_with_llm(
                doc.page_content[:max_chars],
                self.llm,
                persist=False,
            )
        try:
            graph.save()
        except Exception as e:
            self.logger.warning("图谱落盘失败: %s", e)
        return count

    def list_tenant_docs(self, tenant_id: str = "default") -> list[dict]:
        """列出租户 docs 目录下的文件。"""
        from application.tenancy import tenant_docs_dir

        root = tenant_docs_dir(self.project_root, tenant_id)
        if not root.is_dir():
            return []
        out: list[dict] = []
        for p in sorted(root.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(root)).replace("\\", "/")
                out.append({"name": p.name, "size": p.stat().st_size, "path": rel})
        return out

    # ===== 聊天 =====
    async def ask_chat(
        self,
        user_input: str,
        session_id: str = "default",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        active_file: str | None = None,
        files: list | None = None,
    ) -> str:
        """带会话历史的普通对话（四子系统 MemoryFacade + Solip + Skills）。

        api_key / api_base / model_name 为本轮可选覆盖；不传则用 .env。
        active_file：当前打开文件路径（相对或绝对），供条件技能参考。
        files：打开文件内容，在 Skill 解析之后再拼进提问（避免破坏 /skill 匹配）。

        若用户输入以 ``/skill-name`` 开头，会注入对应 SKILL.md 正文到 system。
        """
        blocked = await self.security.guard(user_input, rate_limit=True)
        if blocked:
            return blocked

        if not active_file and files:
            first = files[0]
            if isinstance(first, dict):
                active_file = first.get("path")
            else:
                active_file = getattr(first, "path", None)

        # ---- Skills：解析 /explain 等 slash 命令（必须用原始 user_input）----
        memory_session_id = session_id
        effective_input = user_input
        skill_extra = ""
        skill_temp: float | None = None
        skill_model: str | None = None
        try:
            (
                effective_input,
                skill_extra,
                memory_session_id,
                _resolved,
                skill_temp,
                skill_model,
            ) = await self._resolve_skill_for_turn(
                user_input,
                session_id,
                active_file=active_file,
            )
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            # 技能子系统故障不阻断普通对话
            self.logger.warning("Skills 解析失败，回退普通对话: %s", e)

        # Skill 展开后再拼打开文件，避免 files 前缀挡住 /^\/skill/
        files_prefix = self._build_files_prefix(files)
        llm_input = (
            files_prefix + "用户请求：\n" + effective_input
            if files_prefix
            else effective_input
        )

        llm = self._resolve_llm(
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            temperature=skill_temp,
        )

        try:
            if self.memory is None:
                await self.init_session_store()

            summary_block = ""
            history: list = []
            if self.memory is not None:
                turn = await self.memory.load_turn_context(
                    memory_session_id, effective_input
                )
                summary_block = turn.system_extra()
                for msg in turn.recent_messages:
                    if msg["role"] == "user":
                        history.append(HumanMessage(content=msg.get("content") or ""))
                    elif msg["role"] == "assistant":
                        history.append(AIMessage(content=msg.get("content") or ""))

            # summary_block + skill_extra 一并注入 system
            system_extra = (summary_block or "") + (skill_extra or "")

            prompt = ChatPromptTemplate.from_messages([
                (
                    "system",
                    "你是一个优秀的AI助手, 请简洁准确地回答用户问题。\n"
                    "若系统提供了【相关记忆 / Solip 假设】，可作参考，"
                    "但不要当成用户已确认的事实强行使用。\n"
                    "若系统提供了 # Active Skill，请优先遵循该技能说明。\n"
                    "{summary_block}",
                ),
                MessagesPlaceholder(variable_name="history"),
                ("human", "{input}"),
            ])
            chain = prompt | llm | StrOutputParser()

            result = chain.invoke({
                "input": llm_input,
                "history": history,
                "summary_block": system_extra,
            })
            if not isinstance(result, str):
                result = "" if result is None else str(result)
            if not result.strip():
                return "对话出错: 模型返回空内容，请重试或检查 API Key / 模型设置"

            out_ok, out_reason = self.content_filter.check_output(result)
            if not out_ok:
                return f"[安全拦截] {out_reason}"

            # 历史落库：保留用户原始输入（含 /explain），便于会话列表回看
            persist_user = user_input
            if self.memory is not None:
                memory = self.memory
                await memory.persist_turn(
                    session_id=memory_session_id,
                    user_input=persist_user,
                    assistant_output=result,
                )

                async def _bg_compact() -> None:
                    try:
                        await memory.compact_after_turn(
                            session_id=memory_session_id,
                            user_input=persist_user,
                            assistant_output=result,
                        )
                    except Exception as exc:  # noqa: BLE001
                        self.logger.warning("后台 Solip/Compact 失败: %s", exc)

                asyncio.create_task(_bg_compact())
            elif self.session_store:
                await self.session_store.add_message(
                    memory_session_id, "user", persist_user
                )
                await self.session_store.add_message(
                    memory_session_id, "assistant", result
                )
            return result
        except Exception as e:
            self.logger.error("对话失败: %s", e)
            return f"对话出错: {sanitize_exception_message(e)}"

    def get_session_memory_snapshot(self, session_id: str) -> dict:
        """返回摘要 + Solip 下一问，供 GET /api/sessions/{id}/memory。"""
        if not self.memory:
            return {
                "session_id": session_id,
                "intent_hypothesis": "",
                "open_loops": [],
                "next_questions": [],
                "summary": "",
            }
        return self.memory.get_solip(session_id)

    # ===== RAG =====
    async def ask_rag(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        """混合检索 RAG：路由 →（稠密∪BM25 + RRF）→ Prompt → LLM。

        返回 (answer, sources)；sources 附带 route / rrf_score / dense_rank / sparse_rank。
        """
        from billing.usage import LEDGER
        from observability.tracing import trace
        from langchain_core.output_parsers import StrOutputParser

        from application.tenancy import tenant_bm25_path
        from rag.hybrid_retriever import HybridRetriever
        from rag.query_router import RouteDecision, route_query
        from rag.rag_chain import RAG_PROMPT, format_docs
        from rag.sparse_bm25 import BM25SparseIndex

        blocked = await self.security.guard(question, rate_limit=True)
        if blocked:
            return blocked, []

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        store = self._vector_store_for_tenant(tenant_id)
        bm25 = BM25SparseIndex.load(tenant_bm25_path(self.project_root, tenant_id))

        if self.settings.hybrid_use_router:
            decision = route_query(question)
        else:
            decision = RouteDecision("hybrid", "router 关闭，强制 hybrid")

        if not self.settings.hybrid_retrieval_enabled:
            decision = RouteDecision("dense", "HYBRID_RETRIEVAL_ENABLED=false")

        retriever = HybridRetriever(
            store,
            bm25,
            top_k=self.settings.retrieval_top_k,
            fetch_k=self.settings.hybrid_fetch_k,
            rrf_k=self.settings.hybrid_rrf_k,
            mode=decision.strategy,
        )

        sources: list[dict] = []
        try:
            hits = retriever.retrieve(question)
            docs = [h.doc for h in hits]
            sources = self._docs_to_sources(docs)
            for i, h in enumerate(hits):
                if i < len(sources):
                    sources[i]["rrf_score"] = round(h.rrf_score, 6)
                    sources[i]["dense_rank"] = h.dense_rank
                    sources[i]["sparse_rank"] = h.sparse_rank
                    sources[i]["route"] = decision.strategy
        except Exception as e:
            self.logger.error("混合检索失败，回退纯向量: %s", e)
            try:
                docs = store.similarity_search(question, k=self.settings.retrieval_top_k)
            except Exception as e2:
                return f"问答出错: {sanitize_exception_message(e2)}", []
            sources = self._docs_to_sources(docs)

        # 检索完成后再判断。没有非空正文就拒答，不把问题交给大模型
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
            self.logger.error("RAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", sources

    async def ask_consult(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        session_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        """结构化咨询：缺关键因子就追问，齐了再混合检索。"""
        from application.tenancy import (
            tenant_bm25_path,
            tenant_factor_records_path,
            tenant_factor_session_path,
        )
        from rag.hybrid_retriever import HybridRetriever
        from rag.rag_chain import format_docs
        from rag.sparse_bm25 import BM25SparseIndex
        from rag.structured.consult import run_consult
        from rag.structured.records import (
            load_record,
            load_session_factors,
            save_session_factors,
        )

        blocked = await self.security.guard(question, rate_limit=True)
        if blocked:
            return blocked, []

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        records = load_record(tenant_factor_records_path(self.project_root, tenant_id))
        state_path = tenant_factor_session_path(
            self.project_root, tenant_id, session_id
        )
        factors = load_session_factors(state_path, suffix="")

        store = self._vector_store_for_tenant(tenant_id)
        bm25 = BM25SparseIndex.load(tenant_bm25_path(self.project_root, tenant_id))
        hybrid = HybridRetriever(
            store,
            bm25,
            top_k=self.settings.retrieval_top_k,
            fetch_k=self.settings.hybrid_fetch_k,
            rrf_k=self.settings.hybrid_rrf_k,
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
            self.logger.error("consult 失败: %s", e)
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

    # ===== GraphRAG =====
    async def ask_graph_rag(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        """向量检索 + 知识图谱增强问答，返回 (answer, sources)。"""
        from billing.usage import LEDGER
        from observability.tracing import trace
        from rag.knowledge_graph import GraphRAGRetriever

        blocked = await self.security.guard(question, rate_limit=True)
        if blocked:
            return blocked, []

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        store = self._vector_store_for_tenant(tenant_id)
        graph = self._graph_for_tenant(tenant_id)
        retriever = GraphRAGRetriever(
            store,
            graph,
            depth=self.settings.graph_rag_depth,
            top_k=self.settings.retrieval_top_k,
        )

        try:
            docs = store.similarity_search(question, k=self.settings.retrieval_top_k)
            sources = self._docs_to_sources(docs)
        except Exception:
            sources = []

        chain = create_graph_rag_chain(
            llm,
            retriever,
            top_k=self.settings.retrieval_top_k,
        )
        try:
            result = chain.invoke({"question": question})
            answer = result if isinstance(result, str) else str(result)
            LEDGER.add(tenant_id, requests=1)
            trace("graph_rag_ask", tenant_id=tenant_id, hits=len(sources))
            return answer, sources
        except Exception as e:
            self.logger.error("GraphRAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}", sources

    @staticmethod
    def _build_files_prefix(files: list | None) -> str:
        """把本轮打开的文件拼进任务前缀，减少 Agent 先读盘的往返。"""
        if not files:
            return ""
        chunks: list[str] = []
        for f in files:
            path = getattr(f, "path", None) or (f.get("path") if isinstance(f, dict) else "")
            content = getattr(f, "content", None) or (
                f.get("content") if isinstance(f, dict) else ""
            )
            if not path:
                continue
            text = content if isinstance(content, str) else str(content)
            if len(text) > 6000:
                text = text[:6000] + f"\n... 已截断，原 {len(content)} 字符"
            chunks.append(f"### FILE: {path}\n```\n{text}\n```")
        if not chunks:
            return ""
        return "以下是用户工作区中已打开的文件：\n\n" + "\n\n".join(chunks) + "\n\n"

    # ===== 单 Agent =====
    async def ask_agent(
        self,
        task: str,
        agent_name: str = "assistant",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        workspace_root: str | None = None,
        files: list | None = None,
        active_file: str | None = None,
        e2e_base_url: str | None = None,
        qa_tenant_id: str | None = None,
    ) -> str:
        """运行 ReAct Agent；若带 workspace_root 则注入工作区读写工具。

        支持 slash Skills：``/explain ...`` 会把技能正文拼进 system_prompt。
        ``e2e_base_url`` 或 ``/e2e`` 时接入 Playwright MCP 浏览器工具（不写 spec）；
        ``qa_tenant_id`` 预检索暂关。
        """
        blocked = await self.security.guard(task, rate_limit=True)
        if blocked:
            return blocked

        # 从已打开文件推断 active_file（条件技能 / 日志用）
        if not active_file and files:
            first = files[0]
            if isinstance(first, dict):
                active_file = first.get("path")
            else:
                active_file = getattr(first, "path", None)

        effective_task = task
        skill_extra = ""
        skill_temp: float | None = None
        skill_model: str | None = None
        try:
            (
                effective_task,
                skill_extra,
                _sid,
                resolved,
                skill_temp,
                skill_model,
            ) = await self._resolve_skill_for_turn(
                task,
                session_id="agent",
                active_file=active_file,
            )
            # 技能 frontmatter.agent 可覆盖本轮 agent 角色名
            if resolved is not None and getattr(resolved.command, "agent", None):
                agent_name = resolved.command.agent  # type: ignore[assignment]
        except AppError:
            raise
        except Exception as e:  # noqa: BLE001
            self.logger.warning("Skills 解析失败，回退普通 Agent: %s", e)

        llm = self._resolve_llm(
            api_key=api_key,
            api_base=api_base,
            model_name=skill_model or model_name,
            temperature=skill_temp,
        )

        # 是否进入 E2E：显式 base_url，或 /e2e / 技能名 e2e
        locked = (e2e_base_url or "").strip()
        skill_name = ""
        if resolved is not None:
            cmd = getattr(resolved, "command", None)
            skill_name = (getattr(cmd, "name", None) or "").strip()
        e2e_mode = bool(
            locked
            or skill_name == "e2e"
            or (task or "").lstrip().startswith("/e2e")
        )

        tools = list(self.tool_registry.get_all_tools())
        system_prompt = None
        max_calls = 16

        if workspace_root and not e2e_mode:
            try:
                tools = tools + make_workspace_tools(workspace_root)
                system_prompt = (
                    "你是编程助手，使用 ReAct 框架。可用工具:\n\n{tools_description}\n\n"
                    "请按以下格式响应:\n\n"
                    "Thought: [...]\n"
                    "Action: [工具名]\n"
                    "Action Input: [JSON]\n"
                    "Observation: [工具结果]\n"
                    "...\n"
                    "Final Answer: [最终答复]\n\n"
                    "规则:\n"
                    "1. 每次只调用一个工具；Action Input 必须是有效 JSON\n"
                    "2. 工作区路径一律用相对路径（如 src/app.py），不要写绝对路径\n"
                    "3. 用户要求修改/生成代码时，必须调用 write_workspace_file 写入磁盘，"
                    "不要只在 Final Answer 里贴代码\n"
                    "4. 写入前若不确定当前内容，先 read_workspace_file\n"
                    "5. 可用 list_workspace_dir 浏览目录\n"
                )
            except Exception as e:
                self.logger.warning("注入工作区工具失败: %s", e)

        # 测试知识库 RAG：暂关（缺 EMBEDDING_API_KEY 时会挡 E2E）
        # if (qa_tenant_id or "").strip(): ...

        if skill_extra and not e2e_mode:
            if system_prompt:
                system_prompt = system_prompt + skill_extra
            else:
                system_prompt = (
                    "你是通用助手，使用 ReAct 框架。可用工具:\n\n{tools_description}\n\n"
                    "请按 Thought/Action/Action Input/Observation/Final Answer 格式响应。\n"
                    + skill_extra
                )

        prefix = self._build_files_prefix(files)
        full_task = prefix + "用户请求：\n" + effective_task

        # ---- E2E：有状态 Playwright MCP（官方工具，不写 spec）----
        if e2e_mode:
            from e2e.mcp_playwright import e2e_system_hint, playwright_mcp_session

            hint = e2e_system_hint(
                locked_url=locked or None,
                user=(self.settings.e2e_user or "").strip(),
                password=(self.settings.e2e_password or "").strip(),
            )
            if skill_extra:
                hint = hint + skill_extra
            system_prompt = (
                "你是 E2E 测试助手，使用 ReAct。可用工具:\n\n{tools_description}\n\n"
                "格式: Thought / Action / Action Input / Observation / Final Answer\n"
                + hint
            )
            max_calls = 24
            try:
                async with playwright_mcp_session(locked_url=locked or None) as mcp_tools:
                    agent = ReActAgent(
                        name=agent_name,
                        role="E2E测试助手",
                        llm=llm,
                        tools=list(mcp_tools),
                        system_prompt=system_prompt,
                        max_tool_calls=max_calls,
                    )
                    result = await agent.run(full_task)
                    return result.get("result", "无结果")
            except Exception as e:  # noqa: BLE001
                self.logger.error("Playwright MCP 失败: %s", e)
                return f"E2E 启动失败: {sanitize_exception_message(e)}"

        if system_prompt is None:
            system_prompt = (
                "你是通用助手，使用 ReAct 框架。可用工具:\n\n{tools_description}\n\n"
                "请按 Thought/Action/Action Input/Observation/Final Answer 格式响应。"
            )

        agent = ReActAgent(
            name=agent_name,
            role="编程助手" if workspace_root else "通用助手",
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_tool_calls=max_calls,
        )
        result = await agent.run(full_task)
        return result.get("result", "无结果")

    # ===== 多 Agent =====
    async def ask_multi_agent(
        self,
        task: str,
        mode: str = "sequential",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
        use_tool_calling: bool = True,
    ) -> dict:
        """每请求独立 Orchestrator，避免并发串模型。

        返回::
            {
              "final_answer": str,
              "execution_log": list[str],
              "agent_outputs": dict,
              "total_time_ms": float,
              "success": bool,
            }
        """
        from agents.orchestrator import MultiAgentOrchestrator
        from agents.react_agent import RESEARCHER_SYSTEM_PROMPT, ReActAgent
        from agents.tool_calling_agent import ToolCallingAgent
        from billing.usage import LEDGER
        from infrastructure.llm.openai_compat import create_chat_openai
        from observability.tracing import trace

        blocked = await self.security.guard(task, rate_limit=True)
        if blocked:
            return {
                "final_answer": blocked,
                "execution_log": [],
                "agent_outputs": {},
                "total_time_ms": 0,
                "success": False,
            }

        key = (api_key or "").strip() or (self.settings.deepseek_api_key or "").strip()
        base = (api_base or "").strip() or (self.settings.deepseek_api_base or "").strip()
        model = (model_name or "").strip() or (self.settings.model_name or "").strip()

        orch = MultiAgentOrchestrator()
        web = self.tool_registry.get_tool("web_search")
        read = self.tool_registry.get_tool("read_file")
        code = self.tool_registry.get_tool("execute_python")

        # 优先原生 tool calling（ChatOpenAI）；失败则回退 ReAct
        agents_ready = False
        if use_tool_calling and key and base:
            try:
                tc_llm = create_chat_openai(
                    api_key=key,
                    api_base=base,
                    model=model,
                    temperature=self.settings.model_temperature,
                    max_tokens=self.settings.model_max_tokens,
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="researcher",
                        role="信息研究员",
                        llm=tc_llm,
                        tools=[t for t in [web] if t],
                        system_prompt=RESEARCHER_SYSTEM_PROMPT
                        or "你是信息研究员，需要时调用 web_search。",
                    )
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="coder",
                        role="程序员",
                        llm=tc_llm,
                        tools=[t for t in [read, code] if t],
                        system_prompt="你是程序员，优先用工具读文件/执行代码。",
                    )
                )
                orch.register_agent(
                    ToolCallingAgent(
                        name="reviewer",
                        role="代码审查员",
                        llm=tc_llm,
                        tools=[t for t in [read] if t],
                        system_prompt="你是代码审查员，基于证据给出审查意见。",
                    )
                )
                agents_ready = True
            except Exception as e:  # noqa: BLE001
                self.logger.warning("tool calling 初始化失败，回退 ReAct: %s", e)

        if not agents_ready:
            llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
            orch.register_agent(
                ReActAgent(
                    name="researcher",
                    role="信息研究员",
                    llm=llm,
                    tools=[t for t in [web] if t],
                    system_prompt=RESEARCHER_SYSTEM_PROMPT,
                    max_tool_calls=6,
                )
            )
            orch.register_agent(
                ReActAgent(
                    name="coder",
                    role="程序员",
                    llm=llm,
                    tools=[t for t in [read, code] if t],
                )
            )
            orch.register_agent(
                ReActAgent(
                    name="reviewer",
                    role="代码审查员",
                    llm=llm,
                    tools=[t for t in [read] if t],
                )
            )

        from agents.graphs.multi_agent_graph import run_multi_agent_graph
        result = await run_multi_agent_graph(
            orch.agents,
            task,
            mode=mode,
            debate_rounds=2,
        )

        LEDGER.add("default", requests=1)
        trace("multi_agent", mode=mode, success=result.success)

        # 压缩 agent_outputs，带上 trace（若有）
        outputs: dict = {}
        for name, raw in (result.agent_outputs or {}).items():
            if isinstance(raw, dict):
                outputs[name] = {
                    "result": raw.get("result"),
                    "trace": raw.get("trace", []),
                }
            else:
                outputs[name] = {"result": str(raw), "trace": []}

        return {
            "final_answer": result.final_answer,
            "execution_log": list(result.execution_log or []),
            "agent_outputs": outputs,
            "total_time_ms": result.total_time_ms,
            "success": result.success,
        }

    # ===== 会话 =====
    async def get_chat_history(self, session_id: str, n: int = 20) -> list[dict]:
        if not self.session_store:
            await self.init_session_store()
        return await self.session_store.get_recent_messages(session_id, n)

    async def list_sessions(self) -> list[str]:
        if not self.session_store:
            await self.init_session_store()
        return await self.session_store.list_sessions()

    async def delete_session(self, session_id: str) -> None:
        if not self.session_store:
            await self.init_session_store()
        await self.session_store.clear_session(session_id)
        if self.memory is not None:
            self.memory.forget_session(session_id)

    def get_graph_stats(self) -> dict:
        """返回知识图谱统计（含持久化路径）。"""
        return self.knowledge_graph.get_graph_stats()
