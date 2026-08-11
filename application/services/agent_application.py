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

from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from agents.orchestrator import MultiAgentOrchestrator
from agents.react_agent import ReActAgent
from agents.tools_registry import create_default_registry, make_workspace_tools
from application.security_policy import SecurityPolicy
from config.settings import get_settings
from memory.history_compressor import HistoryCompressor
from memory.session_store import create_session_store
from rag.document_loader import DocumentLoader
from rag.knowledge_graph import GraphRAGRetriever, KnowledgeGraph
from rag.rag_chain import create_graph_rag_chain, create_rag_chain
from rag.vector_store import VectorStoreManager
from safety.content_filter import ContentFilter
from safety.rate_limiter import AsyncRateLimiter
from safety.retry_handler import CircuitBreaker
from shared.errors import AppError, ErrorCode, sanitize_exception_message
from shared.path_security import PathSecurityError, get_project_root, resolve_safe_path
from utils.logger import setup_logger

# 优先使用 infrastructure 中的 ChatModel；兼容旧 llm_deepseek 导入路径
try:
    from infrastructure.llm.deepseek import DeepSeekChatModel
except ImportError:  # pragma: no cover
    from llm_deepseek import DeepSeekChatModel


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
        self._session_summaries: dict[str, str] = {}

        self.history_compressor = HistoryCompressor(
            llm=self.llm,
            window_size=self.settings.memory_window_size,
        )

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
        )

        self.orchestrator = MultiAgentOrchestrator(
            max_rounds=self.settings.max_agent_iterations,
        )
        self._register_default_agents()

        self.rate_limiter = AsyncRateLimiter(
            max_requests=self.settings.rate_limit_requests,
        )
        self.content_filter = ContentFilter(
            blocked_keywords=self.settings.blocked_keywords,
        )
        self.security = SecurityPolicy(self.content_filter, self.rate_limiter)
        self.circuit_breaker = CircuitBreaker(failure_threshold=5)

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
    ) -> DeepSeekChatModel:
        """根据「本轮请求」解析出要使用的 ChatModel。

        优先级（从高到低）：
        1. 本次参数（前端 Settings 传来的）
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
            temperature=self.settings.model_temperature,
            max_tokens=self.settings.model_max_tokens,
            api_key=key,
            api_base=base,
        )

    def _register_default_agents(self) -> None:
        """一次性注册多 Agent 角色，避免每次 ask_multi_agent 重复覆盖。"""
        web = self.tool_registry.get_tool("web_search")
        read = self.tool_registry.get_tool("read_file")
        code = self.tool_registry.get_tool("execute_python")
        self.orchestrator.register_agent(
            ReActAgent(
                name="researcher",
                role="信息研究员",
                llm=self.llm,
                tools=[t for t in [web] if t],
            )
        )
        self.orchestrator.register_agent(
            ReActAgent(
                name="coder",
                role="程序员",
                llm=self.llm,
                tools=[t for t in [read, code] if t],
            )
        )
        self.orchestrator.register_agent(
            ReActAgent(
                name="reviewer",
                role="代码审查员",
                llm=self.llm,
                tools=[t for t in [read] if t],
            )
        )

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

    # ===== 知识库构建 =====
    def build_knowledge_base(self, doc_dir: str) -> int:
        """从本地目录构建向量库，并抽取三元组写入图谱（自动落盘）。

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

        self.logger.info("开始构建知识库: %s", safe_dir)
        docs = self.doc_loader.load_directory(safe_dir)
        if not docs:
            self.logger.warning("未找到任何文档")
            return 0

        count = self.vector_store.add_documents(docs)
        self.logger.info("知识库构建完成, 共 %s 个文档片段", count)

        max_chars = self.settings.graph_extract_max_chars
        for doc in docs:
            self.knowledge_graph.extract_triples_with_llm(
                doc.page_content[:max_chars],
                self.llm,
                persist=False,
            )
        # 批量抽取后统一落盘，降低 IO
        try:
            self.knowledge_graph.save()
        except Exception as e:
            self.logger.warning("图谱落盘失败: %s", e)
        return count

    # ===== 聊天 =====
    async def ask_chat(
        self,
        user_input: str,
        session_id: str = "default",
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> str:
        """带会话历史的普通对话（接入安全策略 + 可选历史压缩）。

        api_key / api_base / model_name 为本轮可选覆盖；不传则用 .env。
        """
        blocked = await self.security.guard(user_input, rate_limit=True)
        if blocked:
            return blocked

        # 本轮专用模型（请求级优先，避免污染单例 self.llm）
        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)

        prompt = ChatPromptTemplate.from_messages([
            ("system", "你是一个优秀的AI助手, 请简洁准确地回答用户问题。\n{summary_block}"),
            MessagesPlaceholder(variable_name="history"),
            ("human", "{input}"),
        ])
        chain = prompt | llm | StrOutputParser()

        history: list = []
        summary_block = ""
        if self.session_store:
            raw = await self.session_store.get_recent_messages(
                session_id, n=self.settings.memory_window_size
            )
            # 长会话：触发摘要压缩，摘要放入 system，窗口消息仍进 history
            if self.history_compressor.should_compress(raw):
                try:
                    recent, new_summary = await self.history_compressor.compress(
                        raw,
                        existing_summmary=self._session_summaries.get(session_id, ""),
                    )
                    self._session_summaries[session_id] = new_summary
                    raw = recent
                    if new_summary:
                        summary_block = f"【历史摘要】{new_summary}"
                except Exception as e:
                    self.logger.warning("历史压缩失败，回退滑动窗口: %s", e)

            for msg in raw:
                if msg["role"] == "user":
                    history.append(HumanMessage(content=msg["content"]))
                elif msg["role"] == "assistant":
                    history.append(AIMessage(content=msg["content"]))

        try:
            result = chain.invoke({
                "input": user_input,
                "history": history,
                "summary_block": summary_block,
            })
            out_ok, out_reason = self.content_filter.check_output(result)
            if not out_ok:
                return f"[安全拦截] {out_reason}"

            if self.session_store:
                await self.session_store.add_message(session_id, "user", user_input)
                await self.session_store.add_message(session_id, "assistant", result)
            return result
        except Exception as e:
            self.logger.error("对话失败: %s", e)
            return f"对话出错: {sanitize_exception_message(e)}"

    # ===== RAG =====
    async def ask_rag(
        self,
        question: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> str:
        """向量检索 RAG（内容过滤 + 限流）。"""
        blocked = await self.security.guard(question, rate_limit=True)
        if blocked:
            return blocked

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        retriever = self.vector_store.get_or_create_store().as_retriever(
            search_kwargs={"k": self.settings.retrieval_top_k}
        )
        chain = create_rag_chain(llm, retriever)
        try:
            result = chain.invoke({"question": question})
            return result
        except Exception as e:
            self.logger.error("RAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}"

    # ===== GraphRAG =====
    async def ask_graph_rag(
        self,
        question: str,
        *,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> str:
        """向量检索 + 知识图谱增强问答。

        依赖 ``build_knowledge_base`` 或已落盘的 ``knowledge_graph_path``。
        图谱为空时仍可退化到向量检索；两侧皆空返回明确提示。
        """
        blocked = await self.security.guard(question, rate_limit=True)
        if blocked:
            return blocked

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)

        # 同步 retriever 配置（设置热更新后也一致）
        self.graph_rag_retriever.depth = self.settings.graph_rag_depth
        self.graph_rag_retriever.top_k = self.settings.retrieval_top_k

        chain = create_graph_rag_chain(
            llm,
            self.graph_rag_retriever,
            top_k=self.settings.retrieval_top_k,
        )
        try:
            result = chain.invoke({"question": question})
            return result
        except Exception as e:
            self.logger.error("GraphRAG 问答失败: %s", e)
            return f"问答出错: {sanitize_exception_message(e)}"

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
    ) -> str:
        """运行 ReAct Agent；若带 workspace_root 则注入工作区读写工具。"""
        blocked = await self.security.guard(task, rate_limit=True)
        if blocked:
            return blocked

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        tools = list(self.tool_registry.get_all_tools())
        system_prompt = None
        if workspace_root:
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

        prefix = self._build_files_prefix(files)
        full_task = prefix + "用户请求：\n" + task

        agent = ReActAgent(
            name=agent_name,
            role="编程助手" if workspace_root else "通用助手",
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_tool_calls=16 if workspace_root else 10,
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
    ) -> str:
        """多 Agent 协作：sequential / debate / router。

        临时把编排器内各 Agent 的 llm 换成「本轮凭证」，跑完再还原，
        避免把请求级 Key 留在单例 orchestrator 里。
        """
        blocked = await self.security.guard(task, rate_limit=True)
        if blocked:
            return blocked

        llm = self._resolve_llm(api_key=api_key, api_base=api_base, model_name=model_name)
        # 记下旧 llm，finally 里还原（并发请求时仍有竞态；本 demo 单用户可接受）
        previous = {name: agent.llm for name, agent in self.orchestrator.agents.items()}
        try:
            for agent in self.orchestrator.agents.values():
                agent.llm = llm

            if mode == "sequential":
                result = await self.orchestrator.run_sequential(
                    task, ["researcher", "coder", "reviewer"]
                )
            elif mode == "debate":
                result = await self.orchestrator.run_debate(
                    task, ["researcher", "coder", "reviewer"], rounds=2
                )
            else:
                result = await self.orchestrator.run_router(task, "researcher")

            return result.final_answer
        finally:
            for name, old_llm in previous.items():
                agent = self.orchestrator.agents.get(name)
                if agent is not None:
                    agent.llm = old_llm

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
        self._session_summaries.pop(session_id, None)

    def get_graph_stats(self) -> dict:
        """返回知识图谱统计（含持久化路径）。"""
        return self.knowledge_graph.get_graph_stats()
