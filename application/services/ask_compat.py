"""旧 ask_* / 会话 API 兼容层（Mixin），保持 CLI 与直调签名不变。"""

from __future__ import annotations


class AskCompatMixin:
    """依赖 ``self.use_cases``；由 AgentApplication 混入。"""

    def build_knowledge_base(self, doc_dir: str, tenant_id: str = "default") -> int:
        return self.use_cases.knowledge.build(doc_dir, tenant_id=tenant_id)

    def list_tenant_docs(self, tenant_id: str = "default") -> list[dict]:
        return self.use_cases.knowledge.list_docs(tenant_id=tenant_id)

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
        result = await self.use_cases.chat.execute(
            user_input,
            session_id=session_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            active_file=active_file,
            files=files,
        )
        return result.answer

    def get_session_memory_snapshot(self, session_id: str) -> dict:
        return self.use_cases.session.memory_snapshot(session_id)

    async def ask_rag(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        result = await self.use_cases.rag.execute(
            question,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return result.answer, list(result.meta.get("sources") or [])

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
        result = await self.use_cases.consult.execute(
            question,
            tenant_id=tenant_id,
            session_id=session_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return result.answer, list(result.meta.get("sources") or [])

    async def ask_graph_rag(
        self,
        question: str,
        *,
        tenant_id: str = "default",
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> tuple[str, list[dict]]:
        result = await self.use_cases.graph_rag.execute(
            question,
            tenant_id=tenant_id,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
        )
        return result.answer, list(result.meta.get("sources") or [])

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
        result = await self.use_cases.agent.execute(
            task,
            agent_name=agent_name,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            workspace_root=workspace_root,
            files=files,
            active_file=active_file,
            e2e_base_url=e2e_base_url,
            qa_tenant_id=qa_tenant_id,
        )
        return result.answer

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
        result = await self.use_cases.multi.execute(
            task,
            multi_mode=mode,
            api_key=api_key,
            api_base=api_base,
            model_name=model_name,
            use_tool_calling=use_tool_calling,
        )
        return {
            "final_answer": result.answer,
            "execution_log": list(result.meta.get("execution_log") or []),
            "agent_outputs": dict(result.meta.get("agent_outputs") or {}),
            "total_time_ms": result.meta.get("total_time_ms"),
            "success": result.meta.get("success"),
        }

    async def get_chat_history(self, session_id: str, n: int = 20) -> list[dict]:
        return await self.use_cases.session.get_history(session_id, n=n)

    async def list_sessions(self) -> list[str]:
        return await self.use_cases.session.list_sessions()

    async def delete_session(self, session_id: str) -> None:
        await self.use_cases.session.delete_session(session_id)

    def get_graph_stats(self) -> dict:
        return self.knowledge_graph.get_graph_stats()
