"""每轮事实抽取 —— 对齐 Mem0「extract memories」。

只抽取 durable facts（偏好、地点、约束、身份、目标），不抽寒暄。
失败返回 []（fail-open），由 CompactPipeline 记日志。
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from memory.observability import memory_event, memory_warn

_log = logging.getLogger(__name__)


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.removeprefix("```json").removeprefix("```").strip()
        if t.endswith("```"):
            t = t[: -3].strip()
    return t


async def extract_memories(
    *,
    llm: BaseChatModel,
    user_input: str,
    assistant_output: str,
) -> list[dict[str, Any]]:
    """返回 [{text, kind, importance, ...}]；失败返回 []。"""
    t0 = time.perf_counter()
    prompt = (
        "从本轮对话提取「以后仍有用」的记忆条目（中文）。\n"
        "kind 取值: preference|location|constraint|identity|goal|fact\n"
        "importance: 0~1。若无新事实返回 {\"items\":[]}。\n"
        f"用户: {user_input}\n助手: {(assistant_output or '')[:1500]}\n"
        'JSON: {"items":[{"text":"...","kind":"location","importance":0.9}]}'
    )
    try:
        msg = await llm.ainvoke(
            [
                SystemMessage(content="只输出合法 JSON，不要 markdown。"),
                HumanMessage(content=prompt),
            ]
        )
        raw = msg.content if isinstance(msg.content, str) else str(msg.content)
        data = json.loads(_strip_fences(raw))
        items = data.get("items") if isinstance(data, dict) else data
        out: list[dict[str, Any]] = []
        for it in items or []:
            if not isinstance(it, dict):
                continue
            t = str(it.get("text") or "").strip()
            if not t:
                continue
            out.append(
                {
                    "text": t[:500],
                    "kind": str(it.get("kind") or "fact"),
                    "importance": float(it.get("importance") or 0.5),
                }
            )
        out = out[:8]
        memory_event(
            "fact_extract",
            ok=True,
            count=len(out),
            latency_ms=int((time.perf_counter() - t0) * 1000),
            kinds=[x["kind"] for x in out],
        )
        return out
    except Exception as e:  # noqa: BLE001
        memory_warn(
            "fact_extract_failed",
            e,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return []
