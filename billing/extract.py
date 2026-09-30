"""从 LangChain 消息 / Chunk 抽取 TurnUsage。"""

from __future__ import annotations

from domain.usage import TurnUsage


def usage_from_message(msg: object, *, model: str = "") -> TurnUsage:
    """读 AIMessage.usage_metadata 或 response_metadata.token_usage。"""
    um = getattr(msg, "usage_metadata", None) or {}
    if um:
        return TurnUsage(
            tokens_in=int(um.get("input_tokens") or 0),
            tokens_out=int(um.get("output_tokens") or 0),
            requests=1,
            model=model,
        )
    meta = getattr(msg, "response_metadata", None) or {}
    tu = meta.get("token_usage") or {}
    return TurnUsage(
        tokens_in=int(tu.get("prompt_tokens") or 0),
        tokens_out=int(tu.get("completion_tokens") or 0),
        requests=1,
        model=model or str(meta.get("model_name") or ""),
    )


def merge_usage(a: TurnUsage, b: TurnUsage) -> TurnUsage:
    """多段流式 / 多跳累加。"""
    return TurnUsage(
        tokens_in=a.tokens_in + b.tokens_in,
        tokens_out=a.tokens_out + b.tokens_out,
        requests=max(a.requests, b.requests, 1),
        model=b.model or a.model,
    )
