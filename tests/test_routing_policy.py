"""Provider 路由策略矩阵（不依赖 Cursor SDK）。"""

from __future__ import annotations

import pytest

from application.routing.policy import decide


@pytest.mark.parametrize(
    "mode,message,has_key,provider,reason_prefix",
    [
        ("chat", "你好", False, "deepseek", "no_cursor_key"),
        ("agent", "随便", False, "deepseek", "no_cursor_key"),
        ("rag", "查资料", True, "deepseek", "mode_rag"),
        ("consult", "问因子", True, "deepseek", "mode_consult"),
        ("graph-rag", "图谱", True, "deepseek", "mode_graph-rag"),
        ("multi", "协作", True, "deepseek", "mode_multi"),
        ("agent", "实现功能", True, "cursor", "mode_agent"),
        ("chat", "请改代码一下", True, "cursor", "chat_code_hint"),
        ("chat", "今天天气", True, "deepseek", "default_chat"),
    ],
)
def test_decide_matrix(mode, message, has_key, provider, reason_prefix):
    choice = decide(mode, message, has_cursor_key=has_key)
    assert choice.provider == provider
    assert choice.reason.startswith(reason_prefix) or choice.reason == reason_prefix
