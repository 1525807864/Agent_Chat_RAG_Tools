"""ChatUseCase.astream：安全拦截与完整路径冒烟（mock LLM）。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from application.use_cases.chat import ChatUseCase
from domain.run import StreamEvent


@pytest.mark.asyncio
async def test_astream_blocked_by_security():
    app = MagicMock()
    app.security.guard = AsyncMock(return_value="[安全拦截] x")
    events = [ev async for ev in ChatUseCase(app).astream("bad")]
    assert events[0] == StreamEvent(kind="delta", text="[安全拦截] x")
    assert events[-1].kind == "final"
    assert events[-1].answer == "[安全拦截] x"
    app._resolve_skill_for_turn.assert_not_called()
