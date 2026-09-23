"""编排流式：API 只消费 StreamEvent。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from domain.run import RequestContext, RunResult, StreamEvent
from orchestration.pipeline import ChatOrchestrator


class _FakeSession:
    def __init__(self) -> None:
        self.persisted: list[tuple[str, str, str]] = []

    async def persist_turn(
        self, session_id: str, user_input: str, assistant_output: str
    ) -> None:
        self.persisted.append((session_id, user_input, assistant_output))


class _FakeChat:
    async def astream(self, message: str, **kwargs):
        yield StreamEvent(kind="delta", text="你")
        yield StreamEvent(kind="delta", text="好")
        yield StreamEvent(kind="final", answer="你好")


@pytest.mark.asyncio
async def test_orchestrator_stream_chat_deltas():
    app = SimpleNamespace(
        settings=SimpleNamespace(cursor_api_key="", cursor_model="x"),
        use_cases=SimpleNamespace(chat=_FakeChat(), session=_FakeSession()),
    )
    orch = ChatOrchestrator(app)
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(return_value=None),
    ):
        events = [
            ev
            async for ev in orch.stream(
                RequestContext(message="hi", mode="chat", session_id="s")
            )
        ]
    assert [e.kind for e in events] == ["delta", "delta", "final"]
    assert events[0].text == "你"
    assert events[1].text == "好"
    assert events[-1].answer == "你好"
    # persist 由 ChatUseCase.astream 负责，编排层不再二次落库
    assert app.use_cases.session.persisted == []


@pytest.mark.asyncio
async def test_orchestrator_stream_non_chat_one_shot():
    class Cap:
        name = "rag"

        async def run(self, app, ctx):
            return RunResult(answer="rag-ans", meta={"capability": "rag"})

    app = SimpleNamespace(
        settings=SimpleNamespace(cursor_api_key="", cursor_model="x"),
        use_cases=SimpleNamespace(session=_FakeSession()),
    )
    orch = ChatOrchestrator(app, capabilities={"rag": Cap()})
    with patch(
        "orchestration.pipeline.try_cursor_answer",
        new=AsyncMock(return_value=None),
    ):
        events = [
            ev
            async for ev in orch.stream(RequestContext(message="q", mode="rag"))
        ]
    assert len(events) == 2
    assert events[0] == StreamEvent(kind="delta", text="rag-ans")
    assert events[1].kind == "final"
    assert events[1].answer == "rag-ans"
