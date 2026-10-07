"""指代 / 省略补全 —— 商业 Agent 标配（上下文改写再检索）。

场景：用户先说「我在北京」，再说「今天有雨吗」
→ rewritten = 「北京今天有雨吗」
→ ReAct / web_search / 语义召回都用 rewritten。
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage

from memory.observability import memory_event, memory_warn

_log = logging.getLogger(__name__)

_SHORT_FOLLOWUP = re.compile(
    r"^(那|那么|然后|继续|还有|今天|明天|怎么样|呢|吗|？|\?)"
)


def needs_rewrite(user_input: str) -> bool:
    """启发式：短句 / 跟进语气 / 缺地点的天气类问题需要改写。"""
    text = (user_input or "").strip()
    if not text:
        return False
    if len(text) <= 24:
        return True
    if _SHORT_FOLLOWUP.search(text):
        return True
    if re.search(r"(天气|下雨|气温|拥堵|房价)", text) and "在" not in text:
        return True
    return False


def _strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.removeprefix("```json").removeprefix("```").strip()
        if t.endswith("```"):
            t = t[: -3].strip()
    return t


async def rewrite_user_query(
    *,
    llm: BaseChatModel,
    user_input: str,
    recent_messages: list[dict[str, Any]],
    slots: dict[str, Any] | None,
    summary: str = "",
) -> dict[str, str]:
    """返回 {original, rewritten, reason}；失败时 rewritten=original（fail-open）。"""
    t0 = time.perf_counter()
    original = (user_input or "").strip()
    if not original:
        return {"original": "", "rewritten": "", "reason": "empty"}

    has_loc = bool((slots or {}).get("location"))
    if not needs_rewrite(original) and not has_loc:
        memory_event(
            "query_rewrite",
            reason="skip",
            original_preview=original[:80],
            latency_ms=0,
        )
        return {"original": original, "rewritten": original, "reason": "skip"}

    hist = recent_messages[-6:] if recent_messages else []
    hist_txt = "\n".join(f"{m.get('role')}: {m.get('content')}" for m in hist)
    slots_txt = json.dumps(slots or {}, ensure_ascii=False)

    prompt = (
        "你是对话上下文补全器。把用户「当前短句」改写成独立、可检索的完整问句。\n"
        "规则：\n"
        "1. 结合历史与槽位补全省略的地点/时间/对象；\n"
        "2. 不要回答问题，只输出 JSON；\n"
        "3. 若无需改写，rewritten 等于原句。\n"
        f"槽位: {slots_txt}\n"
        f"摘要: {summary or '无'}\n"
        f"最近对话:\n{hist_txt}\n"
        f"当前用户: {original}\n"
        '输出 JSON: {"rewritten":"...","reason":"..."}'
    )
    try:
        msg = await llm.ainvoke(
            [
                SystemMessage(content="只输出合法 JSON，不要 markdown。"),
                HumanMessage(content=prompt),
            ]
        )
        text = msg.content if isinstance(msg.content, str) else str(msg.content)
        data = json.loads(_strip_fences(text))
        rewritten = str(data.get("rewritten") or original).strip() or original
        reason = str(data.get("reason") or "llm")
        memory_event(
            "query_rewrite",
            reason=reason,
            changed=rewritten != original,
            original_preview=original[:80],
            rewritten_preview=rewritten[:120],
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        return {
            "original": original,
            "rewritten": rewritten,
            "reason": reason,
        }
    except Exception as e:  # noqa: BLE001
        memory_warn(
            "query_rewrite_failed",
            e,
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )
        loc = (slots or {}).get("location") or ""
        if loc and loc not in original:
            rewritten = f"{loc} {original}"
            memory_event(
                "query_rewrite",
                reason="fallback_slot_prefix",
                rewritten_preview=rewritten[:120],
            )
            return {
                "original": original,
                "rewritten": rewritten,
                "reason": "fallback_slot_prefix",
            }
        return {
            "original": original,
            "rewritten": original,
            "reason": f"error:{type(e).__name__}",
        }
