"""领域端口（Port）：由 infrastructure 提供 Adapter 实现。

仅在存在明确扩展点时抽取：会话存储（Redis/SQLite）与知识图谱持久化。
LLM / 向量库暂不抽 Port，避免无第二实现时的过度抽象。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

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
