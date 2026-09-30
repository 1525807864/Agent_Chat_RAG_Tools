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
            tenant_id=ctx.tenant_id,
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
    name = "agent" #能力必须和前端Mode="agent"对上，编排器用这个名字找处理器

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        # 把HTTP请求里的上下文转发给agentUseCase 
        return await app.use_cases.agent.execute(
            ctx.message,                      # 本轮用户原文
            session_id=ctx.session_id,        # ★关键：前端会话 id（已绑租户前缀，如 default__web-xxx）
            tenant_id=ctx.tenant_id,          # 计费用
            agent_name=ctx.agent_name,        # ReActAgent 显示名
            api_key=ctx.api_key,              # 可选覆盖 LLM key
            api_base=ctx.api_base,            # 可选覆盖 API base
            model_name=ctx.model_name,        # 可选覆盖模型名
            workspace_root=ctx.workspace_root,# 有则注入工作区读写工具
            files=ctx.files,                  # 附件前缀
            active_file=ctx.active_file,      # Skills / 文件相关
            e2e_base_url=ctx.e2e_base_url,    # E2E 锁定 URL
            qa_tenant_id=ctx.qa_tenant_id,    # QA 租户（若有）
        )


class MultiCapability:
    name = "multi"

    async def run(self, app: AgentApplication, ctx: RequestContext) -> RunResult:
        return await app.use_cases.multi.execute(
            ctx.message,
            tenant_id=ctx.tenant_id,
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
