"""阶段 4：编排 matrix — mode × provider（Cursor / DeepSeek）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from domain.run import RequestContext, RunResult
from orchestration.pipeline import ChatOrchestrator


class _FakeUseCase:
    def __init__(self, name: str) -> None:
        self.name = name
        self.calls: list[dict] = []

    async def execute(self, message: str, **kwargs) -> RunResult:
        self.calls.append({"message": message, **kwargs})
        return RunResult(
            answer=f"ok:{self.name}",
            meta={"capability": self.name},
        )


class _FakeSession:
    def __init__(self) -> None:
        self.persisted: list[tuple[str, str, str]] = []

    async def persist_turn(
        self, session_id: str, user_input: str, assistant_output: str
    ) -> None:
        self.persisted.append((session_id, user_input, assistant_output))


def _fake_app(*, modes: list[str] | None = None) -> SimpleNamespace:
    modes = modes or ["chat", "rag", "consult", "graph_rag", "agent", "multi"]
    uc = SimpleNamespace(
        chat=_FakeUseCase("chat"),
        rag=_FakeUseCase("rag"),
        consult=_FakeUseCase("consult"),
        graph_rag=_FakeUseCase("graph-rag"),
        agent=_FakeUseCase("agent"),
        multi=_FakeUseCase("multi"),
        session=_FakeSession(),
    )
    return SimpleNamespace(
        settings=SimpleNamespace(cursor_api_key="", cursor_model="composer"),
        use_cases=uc,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mode,attr",
    [
        ("chat", "chat"),
        ("rag", "rag"),
        ("consult", "consult"),
        ("graph-rag", "graph_rag"),
        ("agent", "agent"),
        ("multi", "multi"),
    ],
)
async def test_orchestrator_dispatches_each_mode(mode: str, attr: str):
    app = _fake_app()
    orch = ChatOrchestrator(app)
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(return_value=None),
    ):
        result = await orch.handle(RequestContext(message="hi", mode=mode))
    assert result.answer == f"ok:{getattr(app.use_cases, attr).name}"
    assert result.meta.get("capability") == getattr(app.use_cases, attr).name
    assert len(getattr(app.use_cases, attr).calls) == 1


@pytest.mark.asyncio
async def test_orchestrator_unknown_mode():
    app = _fake_app()
    orch = ChatOrchestrator(app)
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(return_value=None),
    ):
        with pytest.raises(ValueError, match="未知 mode"):
            await orch.handle(RequestContext(message="x", mode="nope"))


@pytest.mark.asyncio
async def test_orchestrator_cursor_provider_short_circuits():
    app = _fake_app()
    orch = ChatOrchestrator(app)
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(
            return_value=("cursor-ans", {"provider": "cursor", "route_reason": "mode_agent"})
        ),
    ):
        result = await orch.handle(
            RequestContext(message="改代码", mode="agent", session_id="s1")
        )
    assert result.answer == "cursor-ans"
    assert result.meta.get("capability") == "cursor"
    assert result.meta.get("provider") == "cursor"
    assert app.use_cases.session.persisted == [("s1", "改代码", "cursor-ans")]
    assert app.use_cases.agent.calls == []


@pytest.mark.asyncio
async def test_orchestrator_prefixes_files_for_non_agent():
    app = _fake_app()
    orch = ChatOrchestrator(app)
    files = [{"path": "a.py", "content": "x=1"}]
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(return_value=None),
    ):
        await orch.handle(
            RequestContext(message="解释", mode="chat", files=files)
        )
    msg = app.use_cases.chat.calls[0]["message"]
    assert "### FILE: a.py" in msg
    assert "解释" in msg
