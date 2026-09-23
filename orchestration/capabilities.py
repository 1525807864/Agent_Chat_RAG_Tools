"""能力插件：每种 mode 一个处理器，便于开闭扩展。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from domain.run import RequestContext, RunResult

if TYPE_CHECKING:
    from application.services.agent_application import AgentApplication


class Capability(Protocol):
    """一种对话能力（chat / rag / …）。"""

    name: str

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult: ...


class ChatCapability:
    name = "chat"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.chat.execute(
            ctx.message,
            session_id=ctx.session_id,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
            active_file=ctx.active_file,
            files=ctx.files,
        )


class RagCapability:
    name = "rag"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.rag.execute(
            ctx.message,
            tenant_id=ctx.tenant_id,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
        )


class ConsultCapability:
    name = "consult"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.consult.execute(
            ctx.message,
            tenant_id=ctx.tenant_id,
            session_id=ctx.session_id,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
        )


class GraphRagCapability:
    name = "graph-rag"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.graph_rag.execute(
            ctx.message,
            tenant_id=ctx.tenant_id,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
        )


class AgentCapability:
    name = "agent"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.agent.execute(
            ctx.message,
            agent_name=ctx.agent_name,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
            workspace_root=ctx.workspace_root,
            files=ctx.files,
            active_file=ctx.active_file,
            e2e_base_url=ctx.e2e_base_url,
            qa_tenant_id=ctx.qa_tenant_id,
        )


class MultiCapability:
    name = "multi"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.multi.execute(
            ctx.message,
            multi_mode=ctx.multi_mode,
            api_key=ctx.api_key,
            api_base=ctx.api_base,
            model_name=ctx.model_name,
        )


def default_capabilities() -> dict[str, Capability]:
    """mode 名 → 能力插件。新增 mode 时在此注册即可。"""
    caps = [
        ChatCapability(),
        RagCapability(),
        ConsultCapability(),
        GraphRagCapability(),
        AgentCapability(),
        MultiCapability(),
    ]
    return {c.name: c for c in caps}
