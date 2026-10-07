"""对齐检查 / 完成度校验：两个 LLM 协议 + 容错 JSON 解析。

失败策略：全部 fail-open —— 超时 / 异常 / 非法 JSON 时返回 error 类 verdict，
由调用方决定放行（见 IntentGuardService）。
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage

from intent.models import (
    ALIGNMENT_VERDICTS,
    COMPLETION_VERDICTS,
    TASK_BLOCKED,
    TASK_DONE,
    TASK_PENDING,
)
from intent.prompts import ALIGNMENT_CHECK_PROMPT, COMPLETENESS_PROMPT


def parse_json_lenient(raw: str) -> dict[str, Any]:
    """容错解析：去围栏 → 直接 loads → 正则取首段大括号（同 Solip 思路）。"""
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


def _checklist_text(tasks: list[dict[str, Any]]) -> str:
    if not tasks:
        return "（尚无子任务）"
    lines = []
    for t in tasks:
        lines.append(
            f"- [{t.get('id', '?')}] {t.get('status', TASK_PENDING)}: {t.get('title', '')}"
        )
    return "\n".join(lines)


class AlignmentChecker:
    """pre-step：判断下一步动作 vs 锚点目标是否对齐。"""

    def __init__(self, llm: BaseChatModel, timeout_seconds: float = 3.0):
        self.llm = llm
        self.timeout_seconds = timeout_seconds

    async def check_step(
        self,
        *,
        anchor_goal: str,
        tasks: list[dict[str, Any]],
        user_task: str,
        thought: str,
        action_name: str,
        action_input: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """返回 {verdict, reason, correction, latency_ms, _msg, _raw}。

        verdict ∈ aligned | drift | irrelevant | timeout | error；
        _msg 是原始 AIMessage（供调用方合并 token 用量）。
        """
        result: dict[str, Any] = {
            "verdict": "aligned",
            "reason": "",
            "correction": "",
            "latency_ms": 0,
            "_msg": None,
            "_raw": "",
        }
        prompt = ALIGNMENT_CHECK_PROMPT.format(
            anchor_goal=(anchor_goal or "")[:2000],
            checklist=_checklist_text(tasks),
            user_task=(user_task or "")[:2000],
            thought=(thought or "")[:2000],
            action_name=action_name or "",
            action_input=json.dumps(action_input or {}, ensure_ascii=False)[:1500],
        )
        t0 = time.perf_counter()
        try:
            msg = await asyncio.wait_for(
                self.llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            result["verdict"] = "timeout"
            result["reason"] = "对齐检查超时"
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return result
        except Exception as e:  # noqa: BLE001
            result["verdict"] = "error"
            result["reason"] = str(e)[:200]
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return result

        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        result["_msg"] = msg
        raw_text = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        result["_raw"] = raw_text
        data = parse_json_lenient(raw_text)
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in ALIGNMENT_VERDICTS:
            result["verdict"] = "error"
            result["reason"] = "检查输出非法: " + raw_text[:100]
            return result
        result["verdict"] = verdict
        result["reason"] = str(data.get("reason") or "")[:200]
        result["correction"] = str(data.get("correction") or "")[:300]
        if verdict == "drift" and not result["correction"]:
            result["correction"] = "请回到用户最初的目标继续执行，不要偏离。"
        return result


class CompletionChecker:
    """post-answer：校验回答对任务清单的完成度，产出闭环/新任务。"""

    def __init__(
        self,
        llm: BaseChatModel,
        timeout_seconds: float = 10.0,
        max_new_tasks: int = 3,
    ):
        self.llm = llm
        self.timeout_seconds = timeout_seconds
        self.max_new_tasks = max_new_tasks

    async def check_answer(
        self,
        *,
        anchor_goal: str,
        tasks: list[dict[str, Any]],
        user_input: str,
        answer: str,
    ) -> dict[str, Any]:
        """返回 {verdict, task_updates, new_tasks, open_summary, latency_ms, _msg}。"""
        result: dict[str, Any] = {
            "verdict": "error",
            "task_updates": [],
            "new_tasks": [],
            "open_summary": "",
            "latency_ms": 0,
            "_msg": None,
        }
        prompt = COMPLETENESS_PROMPT.format(
            anchor_goal=(anchor_goal or "")[:2000],
            checklist=_checklist_text(tasks),
            user_input=(user_input or "")[:2000],
            answer=(answer or "")[:6000],
            max_new=self.max_new_tasks,
        )
        t0 = time.perf_counter()
        try:
            msg = await asyncio.wait_for(
                self.llm.ainvoke([HumanMessage(content=prompt)]),
                timeout=self.timeout_seconds,
            )
        except Exception:  # noqa: BLE001
            result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
            return result

        result["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        result["_msg"] = msg
        raw_text = msg.content if isinstance(msg.content, str) else str(msg.content or "")
        data = parse_json_lenient(raw_text)
        verdict = str(data.get("verdict") or "").strip().lower()
        if verdict not in COMPLETION_VERDICTS:
            return result  # 保持 error
        result["verdict"] = verdict

        for up in data.get("task_updates") or []:
            if not isinstance(up, dict):
                continue
            status = str(up.get("status") or "").strip().lower()
            if status not in (TASK_DONE, TASK_BLOCKED):
                continue
            if not str(up.get("id") or "").strip():
                continue
            result["task_updates"].append(
                {
                    "id": str(up["id"]).strip(),
                    "status": status,
                    "note": str(up.get("note") or "")[:60],
                }
            )

        seen: set[str] = set()
        for nt in data.get("new_tasks") or []:
            if not isinstance(nt, dict):
                continue
            title = str(nt.get("title") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            result["new_tasks"].append(
                {"title": title[:200], "note": str(nt.get("note") or "")[:60]}
            )
            if len(result["new_tasks"]) >= self.max_new_tasks:
                break

        result["open_summary"] = str(data.get("open_summary") or "")[:200]
        return result
