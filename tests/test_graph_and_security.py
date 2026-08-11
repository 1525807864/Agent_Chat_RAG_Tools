"""无 API Key 的最小自检：图谱持久化、路径沙箱、安全策略。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from application.security_policy import SecurityPolicy
from rag.knowledge_graph import GraphRAGRetriever, KnowledgeGraph
from shared.path_security import PathSecurityError, resolve_safe_path
from safety.content_filter import ContentFilter
from safety.rate_limiter import AsyncRateLimiter


def test_knowledge_graph_json_persist(tmp_path: Path) -> None:
    path = tmp_path / "kg.json"
    kg = KnowledgeGraph(persist_path=path, auto_load=False)
    kg.add_triple("Python", "是一种", "编程语言", persist=True)
    kg.add_triple("Python", "用于", "AI", persist=True)
    assert path.exists()

    kg2 = KnowledgeGraph(persist_path=path, auto_load=True)
    stats = kg2.get_graph_stats()
    assert stats["nodes"] >= 2
    assert stats["edges"] >= 2
    assert stats.get("persist_path")

    hit = kg2.query_entity("Python", depth=1)
    assert hit["relations"]


def test_graph_rag_empty_context(tmp_path: Path) -> None:
    class DummyVS:
        def similarity_search(self, query, k=5):
            return []

    kg = KnowledgeGraph(persist_path=tmp_path / "empty.json", auto_load=False)
    retriever = GraphRAGRetriever(DummyVS(), kg, depth=2, top_k=3)
    result = retriever.retrieve("完全不相关的问题xyz")
    assert result["empty"] is True
    assert "未检索到" in result["merged_context"] or "构建知识库" in result["merged_context"]


def test_path_security_blocks_escape(tmp_path: Path) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (data / "ok.txt").write_text("hi", encoding="utf-8")

    ok = resolve_safe_path(
        "data/ok.txt",
        allowed_roots=["data"],
        project_root=tmp_path,
        must_exist=True,
    )
    assert ok.name == "ok.txt"

    with pytest.raises(PathSecurityError):
        resolve_safe_path(
            "../Secrets",
            allowed_roots=["data"],
            project_root=tmp_path,
        )


def test_security_policy_blocks_empty() -> None:
    policy = SecurityPolicy(ContentFilter(), AsyncRateLimiter(max_requests=100))

    async def _run():
        return await policy.guard("   ", rate_limit=False)

    msg = asyncio.run(_run())
    assert msg and "安全拦截" in msg
