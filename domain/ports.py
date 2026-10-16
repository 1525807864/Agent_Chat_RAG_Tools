"""领域端口（Port）：由 infrastructure 提供 Adapter 实现。

已抽取：
- ``SessionStorePort``：Redis / SQLite 会话存储（有第二实现）
- ``KnowledgeGraphPort``：图谱读写

工具侧：``application.tools.ToolGateway`` 统一注册表 + MCP + 主动发现；
Agent 只依赖网关，不直接拼 MultiServerMCPClient。

LLM / 向量库暂不抽 Port：当前只有 DeepSeek / 单一向量实现，
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from domain.access import TenantMember
from domain.jobs import Job
from domain.knowledge import GraphStats, KnowledgeTriple


@runtime_checkable
class SessionStorePort(Protocol):
    """会话历史持久化端口。"""

    async def get_messages(self, session_id: str) -> list[dict]: ...

    async def add_message(self, session_id: str, role: str, content: str) -> None: ...

    async def get_recent_messages(self, session_id: str, n: int = 20) -> list[dict]: ...

    async def clear_session(self, session_id: str) -> None: ...

    async def list_sessions(self) -> list[str]: ...


@runtime_checkable
class KnowledgeGraphPort(Protocol):
    """知识图谱读写端口（内存图 + 落盘）。"""

    def add_triple(
        self,
        subject: str,
        relation: str,
        obj: str,
        metadata: dict | None = None,
    ) -> None: ...

    def extract_triples_with_llm(self, text: str, llm) -> list[tuple]: ...

    def query_entity(self, entity: str, depth: int = 1) -> dict: ...

    def search_related(self, keyword: str, max_results: int = 10) -> list[dict]: ...

    def get_graph_stats(self) -> dict: ...

    def save(self, filepath: str | None = None) -> None: ...

    def load(self, filepath: str | None = None) -> None: ...

    def list_triples(self) -> list[KnowledgeTriple]: ...

    def stats(self) -> GraphStats: ...

@runtime_checkable 
class UsageLedgerPort(Protocol):
    """租户用量账本端口：热路径只允许高频累加，不写mysql"""
    def add(
        self,
        tenant_id: str,
        *,
        requests: int = 1,
        tokens_in: int = 0,
        tokens_out: int = 0,
    )->None:
        """累加一笔用量"""
        ...
    
    def snapshot(self,tenant_id:str | None = None)->dict:
        """读取快照：单租户dict，或全部租户"""
        ...


@runtime_checkable
class MemberStorePort(Protocol):
    """租户成员持久化。"""

    def get(self, tenant_id: str, user_id: str) -> TenantMember | None: ...

    def upsert(
        self, member: TenantMember, *, invited_by: str | None = None
    ) -> None: ...

    def list_members(self, tenant_id: str) -> list[TenantMember]: ...

    def ensure_owner(self, tenant_id: str, user_id: str) -> TenantMember:
        """租户尚无成员时写入 owner；已有成员则返回本人或抛错。"""
        ...


@runtime_checkable
class JobStorePort(Protocol):
    """任务状态持久化（真相源）。"""

    def create(self, job: Job) -> None: ...

    def get(self, job_id: str) -> Job | None: ...

    def save(self, job: Job) -> None: ...

    def count_active(self, tenant_id: str, job_type: str) -> int: ...


@runtime_checkable
class JobQueuePort(Protocol):
    """可靠投递：只传 job_id，Worker 再查库拿 payload。"""

    def enqueue(self, job_id: str) -> None: ...

    def dequeue(self, *, timeout_sec: int = 5) -> str | None: ...