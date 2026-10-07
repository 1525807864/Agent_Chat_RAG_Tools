"""任务拆解器：首轮后台把意图锚点拆成子任务清单（不阻塞首响）。"""

from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from intent.checker import parse_json_lenient
from intent.prompts import DECOMPOSE_PROMPT


class TaskPlanner:
    def __init__(self, llm: BaseChatModel, max_tasks: int = 8, timeout_seconds: float = 20.0):
        self.llm = llm
        self.max_tasks = max_tasks
        self.timeout_seconds = timeout_seconds

    async def decompose(self, *, goal: str) -> list[dict[str, Any]]:
        """返回 [{"title": ...}]；失败返回 []（调用方退化为单任务）。"""
        prompt = DECOMPOSE_PROMPT.format(
            max_tasks=self.max_tasks,
            goal=(goal or "")[:2000],
        )
        try:
            msg = await asyncio.wait_for(
                self.llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.timeout_seconds,
            )
        except Exception:  # noqa: BLE001
            return []
        raw = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        data = parse_json_lenient(raw)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        known_ids: set[str] = set()
        for t in data.get("tasks") or []:
            if not isinstance(t, dict):
                continue
            title = str(t.get("title") or "").strip()
            if not title or title in seen:
                continue 
            seen.add(title)
            # 模型给的id只作依赖边：真正落库id仍用new_task_id()，下面用映射表
            raw_id = str(t.get("id") or "").strip() or f"tmp{len(known_ids)}"
            deps = []
            for d in t.get("depends_on") or []:
                dep = str(d).strip()
                if dep and dep in known_ids and dep != raw_id:
                    deps.append(dep)
            known_ids.add(raw_id)
            items.append({
                "tmp_id":raw_id,
                "title":title[:200],
                "depends_on":deps,
                "acceptance":str(t.get("acceptance") or "").strip()[:80],
            })
            if len(items) >= self.max_tasks:
                break 
        return items 
                    
