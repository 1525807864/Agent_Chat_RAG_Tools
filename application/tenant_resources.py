"""租户级向量库 / 图谱缓存与检索来源转换。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from rag.knowledge_graph import KnowledgeGraph
from rag.vector_store import VectorStoreManager


def docs_to_sources(docs: list) -> list[dict]:
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


class TenantResources:
    """按 tenant_id 懒创建并缓存向量库与图谱。"""

    def __init__(self, settings: Any, project_root: Path) -> None:
        self._settings = settings
        self._root = project_root
        self._vector_stores: dict[str, VectorStoreManager] = {}
        self._graphs: dict[str, KnowledgeGraph] = {}

    def vector_store(self, tenant_id: str) -> VectorStoreManager:
        from application.tenancy import sanitize_tenant_id, tenant_vector_dir

        tid = sanitize_tenant_id(tenant_id)
        if tid not in self._vector_stores:
            persist = tenant_vector_dir(self._root, tid)
            self._vector_stores[tid] = VectorStoreManager(
                embedding_model=self._settings.embedding_model,
                persist_dir=str(persist),
            )
        return self._vector_stores[tid]

    def graph(self, tenant_id: str) -> KnowledgeGraph:
        from application.tenancy import sanitize_tenant_id, tenant_graph_path

        tid = sanitize_tenant_id(tenant_id)
        if tid not in self._graphs:
            path = tenant_graph_path(self._root, tid)
            self._graphs[tid] = KnowledgeGraph(
                persist_path=str(path),
                auto_load=True,
            )
        return self._graphs[tid]
