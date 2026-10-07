"""LangSmith 开关：无密钥 / 关追踪时必须 fail-open。"""

from __future__ import annotations

from types import SimpleNamespace

from observability.langsmith_trace import langsmith_ready, langsmith_turn


def test_langsmith_ready_false_without_key() -> None:
    settings = SimpleNamespace(langsmith_tracing=True, langsmith_api_key="  ")
    assert langsmith_ready(settings) is False


def test_langsmith_ready_false_when_disabled() -> None:
    settings = SimpleNamespace(langsmith_tracing=False, langsmith_api_key="lsv2_x")
    assert langsmith_ready(settings) is False


def test_langsmith_ready_true_when_on() -> None:
    settings = SimpleNamespace(langsmith_tracing=True, langsmith_api_key="lsv2_x")
    assert langsmith_ready(settings) is True


def test_langsmith_turn_yields_when_disabled() -> None:
    ran = False
    ctx = SimpleNamespace(mode="chat", session_id="s", tenant_id="t")
    with langsmith_turn(ctx, name="test"):
        ran = True
    assert ran is True
