"""把 Holmes HTTP 响应解析成领域 TurnUsage，供 ops 路由写入用量账本。

为什么单独做这个文件？
- 普通 chat/agent 走 LangChain AIMessage，可用 billing.extract.usage_from_message
- Holmes 是外部 HTTP JSON，没有 usage_metadata，不能复用 usage_from_message
- 解析逻辑放在 application/ops，路由只负责「调 Holmes → 记账 → 返回」
"""

from __future__ import annotations

from typing import Any

from domain.usage import TurnUsage


def _as_int(value: Any) -> int:
    """把各种脏字段安全转成非负 int；解析失败当 0。"""
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return n if n > 0 else 0


def _pick_usage_dict(data: dict[str, Any]) -> dict[str, Any]:
    """从 Holmes 响应里尽量找到 usage 字典。

    不同版本字段名可能不同，按优先级试：
    1) data["usage"]
    2) data["token_usage"]
    3) data["metadata"]["usage"] / ["token_usage"]
    找不到就返回空 dict（调用方仍会记 requests=1）。
    """
    for key in ("usage", "token_usage"):
        raw = data.get(key)
        if isinstance(raw, dict):
            return raw

    meta = data.get("metadata")
    if isinstance(meta, dict):
        for key in ("usage", "token_usage"):
            raw = meta.get(key)
            if isinstance(raw, dict):
                return raw

    return {}


def turn_from_holmes(data: dict[str, Any], *, model: str = "") -> TurnUsage:
    """Holmes /api/chat 的 JSON → TurnUsage。

    字段兼容（输入 token）：
      prompt_tokens / tokens_in / input_tokens
    字段兼容（输出 token）：
      completion_tokens / tokens_out / output_tokens

    若 Holmes 完全不回 usage：tokens 为 0，但 requests 仍为 1
    （与 orchestration/pipeline.py 对 Cursor 的回退策略一致）。
    """
    if not isinstance(data, dict):
        data = {}

    tu = _pick_usage_dict(data)

    tokens_in = _as_int(
        tu.get("prompt_tokens")
        or tu.get("tokens_in")
        or tu.get("input_tokens")
    )
    tokens_out = _as_int(
        tu.get("completion_tokens")
        or tu.get("tokens_out")
        or tu.get("output_tokens")
    )

    # model：优先调用方传入（body.model / HOLMES_DEFAULT_MODEL），否则用响应里的
    resolved_model = (model or str(tu.get("model") or data.get("model") or "")).strip()

    return TurnUsage(
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        requests=1,  # 对外一轮调查 = 1 次请求；内部多跳由 finalize_turn 再强制一次
        model=resolved_model,
    )