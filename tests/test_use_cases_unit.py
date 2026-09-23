"""阶段 4：UseCase 单测（mock 应用依赖，不打真实 LLM）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.use_cases.chat import ChatUseCase
from application.use_cases.knowledge import KnowledgeBuildUseCase
from application.use_cases.rag import RagUseCase
from application.use_cases.session import SessionUseCase
from domain.run import RunResult


def _app_with_security(*, blocked: str | None = None) -> MagicMock:
    app = MagicMock()
    app.security.guard = AsyncMock(return_value=blocked)
    app.logger = MagicMock()
    return app


@pytest.mark.asyncio
async def test_chat_use_case_blocked_by_security():
    app = _app_with_security(blocked="[安全拦截] 测试")
    result = await ChatUseCase(app).execute("任意")
    assert isinstance(result, RunResult)
    assert result.answer == "[安全拦截] 测试"
    assert result.meta.get("capability") == "chat"
    app._resolve_llm.assert_not_called()


@pytest.mark.asyncio
async def test_rag_use_case_blocked_by_security():
    app = _app_with_security(blocked="[安全拦截] rag")
    result = await RagUseCase(app).execute("问题")
    assert result.answer == "[安全拦截] rag"
    assert result.meta.get("sources") == []


def test_session_memory_snapshot_without_memory():
    app = MagicMock()
    app.memory = None
    snap = SessionUseCase(app).memory_snapshot("s1")
    assert snap["session_id"] == "s1"
    assert snap["summary"] == ""
    assert snap["next_questions"] == []


@pytest.mark.asyncio
async def test_session_persist_turn_via_session_store():
    store = MagicMock()
    store.add_message = AsyncMock()
    app = MagicMock()
    app.memory = None
    app.init_session_store = AsyncMock()
    app.session_store = store

    await SessionUseCase(app).persist_turn("sid", "u", "a")
    assert store.add_message.await_count == 2
    store.add_message.assert_any_await("sid", "user", "u")
    store.add_message.assert_any_await("sid", "assistant", "a")


def test_knowledge_list_docs_missing_dir(tmp_path, monkeypatch):
    app = MagicMock()
    app.project_root = tmp_path
    monkeypatch.setattr(
        "application.tenancy.tenant_docs_dir",
        lambda root, tid: tmp_path / "no_such",
    )
    assert KnowledgeBuildUseCase(app).list_docs("t1") == []


def test_knowledge_list_docs_finds_files(tmp_path, monkeypatch):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "a.txt").write_text("hi", encoding="utf-8")
    app = MagicMock()
    app.project_root = tmp_path
    monkeypatch.setattr(
        "application.tenancy.tenant_docs_dir",
        lambda root, tid: docs,
    )
    rows = KnowledgeBuildUseCase(app).list_docs("t1")
    assert len(rows) == 1
    assert rows[0]["name"] == "a.txt"
    assert rows[0]["path"] == "a.txt"
