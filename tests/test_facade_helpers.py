"""门面辅助模块与 llm_factory 冒烟。"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from application.llm_factory import resolve_request_llm
from application.tenant_resources import docs_to_sources
from shared.errors import AppError


def test_docs_to_sources_helper():
    doc = SimpleNamespace(
        page_content="hello world",
        metadata={"source": "a.md", "page": 1},
    )
    rows = docs_to_sources([doc])
    assert rows[0]["doc_id"] == "a.md"
    assert rows[0]["snippet"] == "hello world"
    assert rows[0]["page"] == 1


def test_resolve_request_llm_requires_key():
    settings = SimpleNamespace(
        deepseek_api_key="",
        deepseek_api_base="https://api.deepseek.com/v1",
        model_name="m",
        model_temperature=0.2,
        model_max_tokens=100,
    )
    with pytest.raises(AppError) as ei:
        resolve_request_llm(settings)
    assert ei.value.http_status == 401


def test_resolve_request_llm_ok(monkeypatch):
    settings = SimpleNamespace(
        deepseek_api_key="sk-test",
        deepseek_api_base="https://api.deepseek.com/v1",
        model_name="deepseek-chat",
        model_temperature=0.3,
        model_max_tokens=256,
    )
    monkeypatch.setattr(
        "application.llm_factory.DeepSeekChatModel",
        lambda **kwargs: kwargs,
    )
    out = resolve_request_llm(settings, model_name="override")
    assert out["model_name"] == "override"
    assert out["api_key"] == "sk-test"
