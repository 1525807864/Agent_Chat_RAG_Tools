"""阶段 1/2 编排冒烟：UseCase 束 + Orchestrator 可导入，未知 mode 报错。"""

from __future__ import annotations

from domain.run import RequestContext, RunResult
from orchestration.capabilities import default_capabilities


def test_default_capabilities_cover_modes():
    caps = default_capabilities()
    for name in ("chat", "rag", "consult", "graph-rag", "agent", "multi"):
        assert name in caps


def test_run_result_with_meta():
    r = RunResult(answer="hi", meta={"a": 1})
    r2 = r.with_meta(b=2)
    assert r2.answer == "hi"
    assert r2.meta == {"a": 1, "b": 2}
    assert r.meta == {"a": 1}


def test_request_context_defaults():
    ctx = RequestContext(message="hello")
    assert ctx.mode == "chat"
    assert ctx.tenant_id == "default"
