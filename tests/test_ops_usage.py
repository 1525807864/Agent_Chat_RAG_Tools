"""ops 用量：Holmes JSON → TurnUsage → OpsAskResponse 字段映射。"""

from __future__ import annotations

from application.ops.usage import turn_from_holmes
from api.routes.ops import OpsAskResponse
from domain.usage import TurnUsage


def test_turn_from_holmes_prompt_completion_tokens():
    turn = turn_from_holmes(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 20}},
        model="openai/deepseek-chat",
    )
    assert turn == TurnUsage(
        tokens_in=10,
        tokens_out=20,
        requests=1,
        model="openai/deepseek-chat",
    )


def test_turn_from_holmes_missing_usage_still_requests_one():
    turn = turn_from_holmes({}, model="openai/deepseek-chat")
    assert turn.tokens_in == 0
    assert turn.tokens_out == 0
    assert turn.requests == 1


def test_ops_ask_response_tenant_usage_camel_case():
    """构造参数必须用 tenantUsage；snake_case 会 TypeError 导致调查 500。"""
    resp = OpsAskResponse(
        analysis="ok",
        usage={"tokens_in": 1, "tokens_out": 2, "tokens_total": 3, "requests": 1},
        tenantUsage={"requests": 5, "tokens_in": 10, "tokens_out": 20},
    )
    dumped = resp.model_dump()
    assert dumped["tenantUsage"]["requests"] == 5
    assert dumped["usage"]["tokens_in"] == 1
