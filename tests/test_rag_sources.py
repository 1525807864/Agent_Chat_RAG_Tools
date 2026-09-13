"""P1 sources 结构测试。"""

from __future__ import annotations

from langchain_core.documents import Document

from application.services.agent_application import AgentApplication


def test_docs_to_sources():
    docs = [
        Document(
            page_content="hello world " * 40,
            metadata={"source": "a.md", "page": 1},
        )
    ]
    sources = AgentApplication._docs_to_sources(docs)
    assert sources[0]["doc_id"] == "a.md"
    assert sources[0]["page"] == 1
    assert len(sources[0]["snippet"]) <= 300
