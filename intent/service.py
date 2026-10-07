"""IntentGuardService：意图守卫统一入口。

职责：
- ensure_anchor：会话首个用户消息建立意图锚点（零 LLM），后台拆子任务
- check_step：pre-step 对齐检查（Agent 每步工具决策后调用），返回 drift 时
  由调用方拦截；同回合连续 drift 触发 re-anchor 逃生阀（用户真实转向）
- finalize_turn：回合后完成度校验，闭环 / 发现子任务，产出未完成提示

状态：进程态（MemoryFacade 的 SessionMemoryState.task_plan）为权威；
memdir session-task-plan 条目与 MySQL P3 表为镜像。无 memory 时进程内 dict 兜底。
失败策略：全部 fail-open，绝不拖垮主对话。
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from intent.checker import AlignmentChecker, CompletionChecker
from intent.models import (
    TASK_BLOCKED,
    TASK_DONE,
    TASK_IN_PROGRESS,
    TASK_PENDING,
    TASK_SKIPPED,
    TASK_STATUS_CN,
    Task,
    TaskPlan,
    _now_iso,
    new_task_id,
)
from intent.planner import TaskPlanner

_log = logging.getLogger(__name__)


class IntentGuardService:
    def __init__(
        self,
        *,
        settings: Any,
        llm: Any,
        memory: Any = None,
        session_id: str = "default",
        tenant_id: str = "default",
        event_sink: Any = None,
        logger: Any = None,
    ):
        self.settings = settings
        self.session_id = session_id
        self.tenant_id = tenant_id
        self.memory = memory
        self.event_sink = event_sink  # P1：asyncio.Queue，向 SSE 推 task 帧
        self.logger = logger or _log
        self.checker = AlignmentChecker(
            llm, timeout_seconds=float(settings.intent_check_timeout_seconds)
        )
        self.completer = CompletionChecker(llm)
        self.planner = TaskPlanner(llm, max_tasks=int(settings.intent_max_tasks))
        self.check_model = str(
            getattr(llm, "model_name", "") or settings.model_name or ""
        )
        # 无 memory 时的进程内兜底
        self._fallback: dict[str, TaskPlan] = {}
        self._own_locks: dict[str, asyncio.Lock] = {}
        # 本回合（同一 guard 实例）统计
        self._turn_checks = 0
        self._turn_errors = 0
        self._turn_drifts = 0
        self._decomposed = False

    # ------------------------------------------------------------------ 状态
    def _get_plan(self) -> TaskPlan | None:
        if self.memory is not None:
            try:
                data = self.memory.get_task_plan(self.session_id)
                if isinstance(data, dict) and data.get("goal"):
                    return TaskPlan.from_dict(data)
            except Exception:  # noqa: BLE001
                pass
            return None
        return self._fallback.get(self.session_id)

    def _set_plan(self, plan: TaskPlan, *, persist: bool = False) -> None:
        """更新进程态；persist=True 时同步写 memdir + MySQL 镜像。"""
        data = plan.to_dict()
        if self.memory is not None:
            try:
                if persist:
                    self.memory.persist_task_plan(self.session_id, data)
                else:
                    self.memory.set_task_plan(self.session_id, data)
            except Exception as e:  # noqa: BLE001
                self.logger.warning("意图台账写进程态失败: %s", e)
                self._fallback[self.session_id] = plan
        else:
            self._fallback[self.session_id] = plan
        if persist:
            self._mirror_mysql(plan)

    def _mirror_mysql(self, plan: TaskPlan) -> None:
        """MySQL P3 表镜像（阻塞 IO 放后台线程，失败吞掉）。"""
        try:
            asyncio.create_task(asyncio.to_thread(self._mirror_mysql_sync, plan))
        except Exception as e:  # noqa: BLE001
            self.logger.warning("意图台账 MySQL 镜像启动失败: %s", e)

    def _mirror_mysql_sync(self, plan: TaskPlan) -> None:
        try:
            from infrastructure.db.intent_store import (
                safe_upsert_anchor,
                safe_upsert_tasks,
            )

            data = plan.to_dict()
            safe_upsert_anchor(
                tenant_id=self.tenant_id,
                session_id=self.session_id,
                plan=data,
            )
            safe_upsert_tasks(
                tenant_id=self.tenant_id,
                session_id=self.session_id,
                anchor_version=plan.version,
                tasks=[t.to_dict() for t in plan.tasks],
            )
        except Exception as e:  # noqa: BLE001
            self.logger.warning("意图台账 MySQL 镜像失败: %s", e)

    def _load_from_mysql(self) -> TaskPlan | None:
        """进程重启且 memdir 缺失时，从 P3 表恢复。"""
        try:
            from infrastructure.db.intent_store import load_plan

            data = load_plan(tenant_id=self.tenant_id, session_id=self.session_id)
            if isinstance(data, dict) and data.get("goal"):
                return TaskPlan.from_dict(data)
        except Exception:  # noqa: BLE001
            pass
        return None

    def _lock(self) -> asyncio.Lock:
        if self.memory is not None and hasattr(self.memory, "lock_for"):
            return self.memory.lock_for(self.session_id)
        if self.session_id not in self._own_locks:
            self._own_locks[self.session_id] = asyncio.Lock()
        return self._own_locks[self.session_id]

    def _emit(self, etype: str, data: dict[str, Any]) -> None:
        """向 SSE 事件队列推一帧（P1 前端用）；无 sink 时静默。"""
        if self.event_sink is None:
            return
        try:
            self.event_sink.put_nowait({"type": etype, "data": data})
        except Exception:  # noqa: BLE001
            pass

    def _record_check(
        self,
        *,
        phase: str,
        step_no: int,
        verdict: str,
        reason: str = "",
        correction: str = "",
        action: dict[str, Any] | None = None,
        latency_ms: int = 0,
    ) -> None:
        """审计落库（后台线程，失败吞掉）。"""
        try:
            from infrastructure.db.intent_store import safe_record_check

            asyncio.create_task(
                asyncio.to_thread(
                    safe_record_check,
                    tenant_id=self.tenant_id,
                    session_id=self.session_id,
                    turn_no=0,
                    step_no=step_no,
                    phase=phase,
                    verdict=str(verdict),
                    reason=str(reason),
                    correction=str(correction),
                    action_json=action,
                    latency_ms=int(latency_ms),
                    model=self.check_model,
                )
            )
        except Exception:  # noqa: BLE001
            pass

    def _emit_plan(self, plan: TaskPlan, etype: str = "plan_update") -> None:
        """前端只认 data.plan.goal。缺 plan 的帧会被丢掉，进度条就不会动。"""
        self._emit(
            etype,
            {
                "plan": plan.to_dict(),
                "progress": plan.progress(),
                "version": plan.version,
            },
        )

    MAX_ATTEMPTS = 3

    def claim_task(self, *, action_name: str) -> Task | None:
        """工具即将执行：把一条 ready 任务标成 in_progress。同一时刻只允许一条。"""
        plan = self._get_plan()
        if plan is None or not plan.tasks:
            return None
        name = (action_name or "").strip()
        active = plan.active_task()
        if active is not None:
            if active.bound_action == name or not active.bound_action:
                active.bound_action = name
                active.attempt += 1
                self._set_plan(plan, persist=True)
                self._emit_plan(plan)
                return active
            return active

        ready = plan.ready_tasks()
        if not ready:
            open_ones = plan.open_tasks()
            if not open_ones:
                return None
            target = open_ones[0]
        else:
            target = ready[0]
        for t in plan.tasks:
            if t.status == TASK_IN_PROGRESS and t.id != target.id:
                t.status = TASK_PENDING
                t.bound_action = ""
        target.status = TASK_IN_PROGRESS
        target.bound_action = name
        target.attempt = max(int(target.attempt or 0), 0) + 1
        self._set_plan(plan, persist=True)
        self._emit_plan(plan)
        return target

    def complete_active_task(self, *, ok: bool, evidence: str = "") -> Task | None:
        """工具 Observation 回来：成功则 done，失败且超限则 blocked。"""
        plan = self._get_plan()
        if plan is None:
            return None
        active = plan.active_task()
        if active is None:
            return None
        active.evidence = (evidence or "")[:400]
        if ok:
            active.status = TASK_DONE
            active.closed_by = "lifecycle"
            active.closed_at = _now_iso()
            active.bound_action = ""
        elif active.attempt >= self.MAX_ATTEMPTS:
            active.status = TASK_BLOCKED
            active.closed_by = "lifecycle"
            active.closed_at = _now_iso()
        else:
            active.status = TASK_PENDING
            active.bound_action = ""
        self._set_plan(plan, persist=True)
        self._emit_plan(plan)
        return active
    async def ensure_anchor(self, *, user_input: str, turn_no: int = 1) -> TaskPlan | None:
        """建立 / 装载意图锚点。首条用户消息原文作锚点（零 LLM 成本、绝不漂移）。"""
        async with self._lock():
            plan = self._get_plan()
            if plan is not None and plan.goal:
                return plan
            plan = self._load_from_mysql()
            if plan is None or not plan.goal:
                goal = (user_input or "").strip()
                if not goal:
                    return None
                plan = TaskPlan(
                    session_id=self.session_id,
                    goal=goal[:2000],
                    goal_raw=goal,
                    turn_created=turn_no,
                )
            self._set_plan(plan, persist=True)
            self._emit(
                "anchor",
                {
                    "goal": plan.goal,
                    "turn_created": plan.turn_created,
                    "version": plan.version,
                },
            )
            self._schedule_decompose(plan)
            return plan

    def _schedule_decompose(self, plan: TaskPlan) -> None:
        """首轮后台拆子任务（不阻塞首响）；已拆过或有任务则跳过。"""
        if self._decomposed or plan.tasks:
            self._decomposed = True
            return
        self._decomposed = True

        async def _bg() -> None:
            try:
                items = await self.planner.decompose(goal=plan.goal)
            except Exception:  # noqa: BLE001
                items = []
            async with self._lock():
                cur = self._get_plan()
                if cur is None or cur.goal != plan.goal:
                    return  # 已 re-anchor，丢弃旧拆解
                if items:
                    tmp_to_real: dict[str,str] = {}
                    built: list[Task] = []
                    for i,x in enumerate(items):
                        tid = new_task_id()
                        tmp_to_real[str(x.get("tmp_id") or "")] = tid 
                        built.append(Task(
                            id = tid,
                            title=str(x.get("title") or "").strip(),
                            sort=i,
                            acceptance=str(x.get("acceptance") or ""),
                        )
                    )
                    for task_obj,x in zip(built,items):
                        task_obj.depends_on = [
                            tmp_to_real[d]
                            for d in (x.get("depends_on") or [])
                            if d in tmp_to_real 
                        ]
                 
                    cur.tasks = built 
                if not cur.tasks:
                    # 拆解失败退化为单任务（= 锚点本身）
                    cur.tasks = [
                        Task(id=new_task_id(), title=cur.goal[:200] or "完成用户目标", sort=0)
                    ]
                self._set_plan(cur, persist=True)
                self._emit_plan(cur)

        asyncio.create_task(_bg())

    # ------------------------------------------------------------ pre-step 检查
    async def check_step(
        self,
        *,
        task: str,
        iteration: int,
        thought: str,
        action_name: str,
        action_input: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """对「下一步动作」做目标对齐检查。

        返回 {verdict, reason, correction, _msg}；verdict=drift 时调用方应拦截
        该动作并注入 correction。同回合连续 drift 达阈值 → re-anchor 后放行。
        """
        result: dict[str, Any] = {
            "verdict": "aligned",
            "reason": "",
            "correction": "",
            "_msg": None,
        }
        async with self._lock():
            plan = self._get_plan()
            if plan is None or not plan.goal:
                return result  # 无锚点（guard 未被 ensure_anchor 初始化）→ 放行

            self._turn_checks += 1
            if self._turn_checks > int(self.settings.intent_check_max_per_turn):
                return result
            if self._turn_errors >= 3:
                # 连续失败短接：本回合剩余检查全跳过，避免无谓延迟
                result["reason"] = "连续检查失败，本回合跳过"
                return result

            check = await self.checker.check_step(
                anchor_goal=plan.goal,
                tasks=[t.to_dict() for t in plan.tasks],
                user_task=task,
                thought=thought,
                action_name=action_name,
                action_input=action_input,
            )
            result["_msg"] = check.get("_msg")
            verdict = check.get("verdict") or "error"
            result["reason"] = check.get("reason", "")
            result["correction"] = check.get("correction", "")

            if verdict in ("error", "timeout"):
                # fail-open：放行该动作，但记录错误
                self._turn_errors += 1
                plan.check_errors += 1
                self._set_plan(plan)
                self._record_check(
                    phase="pre_step",
                    step_no=iteration + 1,
                    verdict=verdict,
                    reason=check.get("reason", ""),
                    action={"tool": action_name, "input": action_input},
                    latency_ms=check.get("latency_ms", 0),
                )
                result["verdict"] = "aligned"
                return result

            self._record_check(
                phase="pre_step",
                step_no=iteration + 1,
                verdict=verdict,
                reason=check.get("reason", ""),
                correction=check.get("correction", ""),
                action={"tool": action_name, "input": action_input},
                latency_ms=check.get("latency_ms", 0),
            )

            if verdict == "drift":
                self._turn_drifts += 1
                plan.drift_count += 1
                plan.last_check = {"verdict": "drift", "reason": check.get("reason", ""), "at": _now_iso()}
                threshold = int(self.settings.intent_drift_reanchor_threshold)
                if self._turn_drifts >= threshold:
                    # 逃生阀：连续偏离 → 判定用户真实转向，re-anchor 后放行
                    self._reanchor_locked(plan, new_goal=task)
                    self._turn_drifts = 0
                    result["verdict"] = "aligned"
                    result["reason"] = "检测到用户转向，已更新目标锚点"
                    result["correction"] = ""
                    return result
                plan.blocked_actions += 1
                self._set_plan(plan, persist=True)
                self._emit(
                    "check",
                    {
                        "step": iteration + 1,
                        "verdict": "drift",
                        "reason": check.get("reason", ""),
                        "correction": check.get("correction", ""),
                    },
                )
                result["verdict"] = "drift"
                return result

            # aligned / irrelevant：放行
            self._turn_drifts = 0
            plan.last_check = {"verdict": verdict, "reason": check.get("reason", ""), "at": _now_iso()}
            self._set_plan(plan)
            result["verdict"] = verdict
            return result

    def _reanchor_locked(self, plan: TaskPlan, *, new_goal: str) -> None:
        """用户真实转向：旧锚点入历史，未闭环任务标 skipped，换新锚点。"""
        plan.anchor_history.append(
            {"goal": plan.goal, "updated_at": _now_iso(), "reason": "用户转向"}
        )
        for t in plan.tasks:
            if t.status not in (TASK_DONE, TASK_BLOCKED, TASK_SKIPPED):
                t.status = TASK_SKIPPED
        goal = (new_goal or "").strip()
        plan.goal = goal[:2000]
        plan.goal_raw = goal
        self._set_plan(plan, persist=True)
        self._emit(
            "anchor",
            {
                "goal": plan.goal,
                "turn_created": plan.turn_created,
                "version": plan.version,
                "replaced": True,
            },
        )
        self.logger.info("意图守卫 re-anchor: %s", plan.goal[:80])

    # ------------------------------------------------------------ 回合收尾
    async def finalize_turn(
        self,
        *,
        user_input: str,
        answer: str,
        turn_no: int = 0,
    ) -> dict[str, Any]:
        """完成度校验：闭环 / 发现子任务，返回未完成任务清单。"""
        empty: dict[str, Any] = {
            "verdict": "complete",
            "task_updates": [],
            "new_tasks": [],
            "open_summary": "",
            "open_tasks": [],
            "plan": None,
            "latency_ms": 0,
        }
        async with self._lock():
            plan = self._get_plan()
            if plan is None or not plan.goal:
                return empty
            check = await self.completer.check_answer(
                anchor_goal=plan.goal,
                tasks=[t.to_dict() for t in plan.tasks],
                user_input=user_input,
                answer=answer,
            )
            self._record_check(
                phase="post_answer",
                step_no=0,
                verdict=check.get("verdict", "error"),
                reason=check.get("open_summary", ""),
                latency_ms=check.get("latency_ms", 0),
            )

            verdict = check.get("verdict", "error")
            if verdict == "error":
                # fail-open：不改台账，按现状返回未闭环清单
                return {
                    **empty,
                    "verdict": "error",
                    "open_tasks": plan.open_task_dicts(),
                    "plan": plan.to_dict(),
                    "latency_ms": check.get("latency_ms", 0),
                }

            # 应用闭环（只允许 done / blocked，有证据才闭环）
            by_id = {t.id: t for t in plan.tasks}
            for up in check.get("task_updates") or []:
                t = by_id.get(str(up.get("id") or ""))
                if t is None or up.get("status") not in (TASK_DONE, TASK_BLOCKED):
                    continue
                t.status = str(up["status"])
                t.closed_by = "check"
                t.closed_at = _now_iso()

            # 发现新子任务（回答中提到但未完成）
            existing = {t.title for t in plan.tasks}
            for nt in check.get("new_tasks") or []:
                title = str(nt.get("title") or "").strip()
                if title and title not in existing:
                    plan.tasks.append(
                        Task(id=new_task_id(), title=title[:200], sort=len(plan.tasks))
                    )
                    existing.add(title)

            if verdict == "complete":
                plan.last_confirmed_turn = turn_no or plan.last_confirmed_turn
            self._set_plan(plan, persist=True)
            # 带完整 plan，前端才能刷新进度；verdict 一并放进 data
            self._emit(
                "finalize",
                {
                    "verdict": verdict,
                    "plan": plan.to_dict(),
                    "progress": plan.progress(),
                    "version": plan.version,
                    "open_tasks": plan.open_task_dicts(),
                    "open_summary": str(check.get("open_summary") or ""),
                },
            )
            return {
                "verdict": verdict,
                "task_updates": check.get("task_updates") or [],
                "new_tasks": check.get("new_tasks") or [],
                "open_summary": str(check.get("open_summary") or ""),
                "open_tasks": plan.open_task_dicts(),
                "plan": plan.to_dict(),
                "latency_ms": check.get("latency_ms", 0),
            }

    # ------------------------------------------------------------ 回合级检查
    async def pre_turn_check(self, *, user_input: str) -> dict[str, Any]:
        """无决策循环模式（chat/rag/consult 等）的回合级检查。

        判断「用户新消息 vs 锚点」：drift（用户转向新话题）→ re-anchor。
        返回 {"verdict": "same|switch|error", "reanchored": bool}。
        """
        result: dict[str, Any] = {"verdict": "same", "reanchored": False}
        plan = self._get_plan()
        if plan is None or not plan.goal:
            return result
        if (user_input or "").strip() == plan.goal:
            # 首轮或与锚点同文的追问，跳过 LLM
            return result
        check = await self.checker.check_step(
            anchor_goal=plan.goal,
            tasks=[t.to_dict() for t in plan.tasks],
            user_task=user_input,
            thought="（本模式无中间步骤，直接判断用户新消息与原始目标的关系）",
            action_name="回答",
            action_input={},
        )
        verdict = check.get("verdict") or "error"
        self._record_check(
            phase="pre_turn",
            step_no=0,
            verdict=verdict,
            reason=check.get("reason", ""),
            latency_ms=check.get("latency_ms", 0),
        )
        if verdict == "drift":
            async with self._lock():
                cur = self._get_plan()
                if cur is not None and cur.goal == plan.goal:
                    self._reanchor_locked(cur, new_goal=user_input)
            result = {"verdict": "switch", "reanchored": True}
        elif verdict in ("error", "timeout"):
            result["verdict"] = "error"
        return result

    async def close_turn(
        self, *, user_input: str, answer: str
    ) -> tuple[str, dict[str, Any]]:
        """回合收尾：完成度校验 + 按需在答案尾部追加【未完成任务清单】。

        返回 (最终答案, meta)（meta 含 task_plan 快照，供响应/SSE done 帧用）。
        """
        try:
            plan = self._get_plan()
            # chat 没有工具环时也要让进度动起来：先认领第一条 ready
            if plan and plan.tasks and plan.active_task() is None:
                self.claim_task(action_name="answer")
            fin = await self.finalize_turn(user_input=user_input, answer=answer)
        except Exception as e:  # noqa: BLE001
            self.logger.warning("意图守卫 close_turn 失败: %s", e)
            return answer, {"task_plan": self.task_plan_meta()}
        meta = {"task_plan": fin.get("plan") or self.task_plan_meta()}
        if (
            self.settings.intent_append_open_tasks_notice
            and fin.get("verdict") != "complete"
            and fin.get("open_tasks")
        ):
            lines = ["\n\n---", "【未完成任务清单】"]
            for i, t in enumerate(fin["open_tasks"], start=1):
                status_cn = TASK_STATUS_CN.get(t.get("status"), "待办")
                lines.append(f"{i}. {t.get('title', '')}（{status_cn}）")
            lines.append('需要继续时可说"继续完成剩余任务"。')
            return answer + "\n".join(lines), meta
        return answer, meta

    # ------------------------------------------------------------------ 只读
    def snapshot(self) -> dict[str, Any] | None:
        plan = self._get_plan()
        return plan.to_dict() if plan else None

    def checklist_text(self) -> str:
        """给前端/日志的人类可读清单。"""
        plan = self._get_plan()
        if plan is None:
            return ""
        return plan.human_text()

    def task_plan_meta(self) -> dict[str, Any]:
        """回合结束后挂进响应 meta 的快照（P1 使用）。"""
        plan = self._get_plan()
        return plan.to_dict() if plan else {}
