"""
Solip 模式：根据当前会话「猜」用户下一问
输出固定 JSON，写入 Memdir (kind=solip, id=session-solip)
失败返回空结构，不阻断主对话
"""
from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

SOLIP_PROMPT = """你是会话分析器（Solip）。根据对话，推断用户「下一句最可能问什么」。
要求：
1. 只输出 JSON（不要 Markdown 代码围栏）。
2. JSON schema:
{{
  "intent_hypothesis": "用户当前总目标，一句话",
  "open_loops": ["尚未闭环的点", "..."],
  "next_questions": [
    {{"question": "可能的下一问", "confidence": 0.0到1.0, "reason": "简短理由"}}
  ]
}}
3. next_questions 最多 {top_k} 条，按 confidence 降序。
4. 不要编造与对话无关的隐私信息。
【历史摘要】
{summary}
【最近对话】
{dialog}
【用户刚问】
{user_input}
【助手刚答】
{assistant_output}
"""


class SolipPredictor:
    def __init__(self, llm: BaseChatModel, top_k: int = 3):
        self.llm = llm
        self.top_k = top_k

    def _dialog_text(self, messages: list[dict], limit: int = 12) -> str:
        chunk = messages[-limit:] if messages else []
        return "\n".join(
            f"{m.get('role', '?')}: {m.get('content', '')}" for m in chunk
        )

    def _parse_json(self, raw: str) -> dict[str, Any]:
        text = (raw or "").strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        try:
            data = json.loads(text)
            return data if isinstance(data, dict) else {}
        except Exception:
            m = re.search(r"\{[\s\S]*\}", text)
            if not m:
                return {}
            try:
                data = json.loads(m.group(0))
                return data if isinstance(data, dict) else {}
            except Exception:
                return {}

    async def predict(
        self,
        *,
        user_input: str,
        assistant_output: str,
        recent_messages: list[dict],
        summary: str = "",
    ) -> dict[str, Any]:
        """返回标准化 solip 结果；出错返回空结构。"""
        empty = {
            "intent_hypothesis": "",
            "open_loops": [],
            "next_questions": [],
        }
        prompt = SOLIP_PROMPT.format(
            top_k=self.top_k,
            summary=summary or "（无）",
            dialog=self._dialog_text(recent_messages),
            user_input=user_input,
            assistant_output=(assistant_output or "")[:2000],
        )
        try:
            raw = self.llm.invoke([HumanMessage(content=prompt)]).content
            data = self._parse_json(str(raw))
        except Exception:
            return empty

        nq = data.get("next_questions") or []
        cleaned = []
        for item in nq[: self.top_k]:
            if isinstance(item, dict) and item.get("question"):
                try:
                    conf = float(item.get("confidence", 0.5))
                except Exception:
                    conf = 0.5
                cleaned.append(
                    {
                        "question": str(item.get("question", "")).strip(),
                        "confidence": max(0.0, min(1.0, conf)),
                        "reason": str(item.get("reason", "")).strip(),
                    }
                )
            elif isinstance(item, str) and item.strip():
                cleaned.append(
                    {"question": item.strip(), "confidence": 0.5, "reason": ""}
                )

        cleaned.sort(key=lambda x: x["confidence"], reverse=True)
        return {
            "intent_hypothesis": str(data.get("intent_hypothesis") or "").strip(),
            "open_loops": [
                str(x).strip()
                for x in (data.get("open_loops") or [])
                if str(x).strip()
            ][:8],
            "next_questions": cleaned,
        }
