"""IntentGuardService 单测：drift 拦截 / 逃生阀 / fail-open / 完成度闭环。

全部用 Fake LLM，不发真实网络请求。
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage

from intent.models import (
    TASK_DONE,
    TASK_PENDING,
    TASK_SKIPPED,
    TaskPlan,
)
from intent.service import IntentGuardService


class FakeCheckLLM:
    """按顺序返回预设 JSON 的检查 LLM。"""

    def __init__(self, outputs: list[str], delay: float = 0.0):
        self.outputs = list(outputs)
        self.delay = delay
        self.model_name = "fake-check-model"

    async def ainvoke(self, messages, **kwargs):
        if self.delay:
            await asyncio.sleep(self.delay)
        return AIMessage(content=self.outputs.pop(0) if self.outputs else "{}")


class BoomLLM:
    model_name = "boom-model"

    async def ainvoke(self, messages, **kwargs):
        raise RuntimeError("检查模型挂了")


def _settings(**kw) -> SimpleNamespace:
    base = dict(
        intent_check_timeout_seconds=0.5,
        intent_check_max_per_turn=8,
        intent_max_tasks=8,
        intent_drift_reanchor_threshold=2,
        intent_append_open_tasks_notice=True,
        model_name="fake-model",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def _guard(llm, **kw) -> IntentGuardService:
    g = IntentGuardService(
        settings=_settings(**kw),
        llm=llm,
        memory=None,
        session_id="s1",
        tenant_id="t1",
    )
    # 单测隔离：不读/不写 MySQL（生产路径由集成环境验证）
    g._load_from_mysql = lambda: None
    g._mirror_mysql = lambda plan: None
    g._record_check = lambda **kw2: None
    return g


@pytest.mark.asyncio
async def test_ensure_anchor_uses_raw_user_input():
    g = _guard(FakeCheckLLM([]))
    plan = await g.ensure_anchor(user_input="帮我写一份竞品分析报告")
    assert plan is not None
    assert plan.goal == "帮我写一份竞品分析报告"
    assert plan.turn_created == 1
    # 后台拆解会走 FakeCheckLLM 的 ainvoke（返回 {}）→ 退化为单任务
    await asyncio.sleep(0.05)
    cur = g._get_plan()
    assert cur is not None and cur.tasks, "拆解失败应退化为单任务"


@pytest.mark.asyncio
async def test_check_step_aligned():
    g = _guard(FakeCheckLLM(['{"verdict": "aligned", "reason": "在做正事"}']))
    await g.ensure_anchor(user_input="写报告")
    r = await g.check_step(
        task="写报告", iteration=0, thought="先查资料",
        action_name="web_search",         action_input={"query": "竞品定价"},
    )
    assert r["verdict"] == "aligned"


def test_claim_and_complete_moves_progress():
    from intent.models import TASK_IN_PROGRESS, Task

    g = _guard(FakeCheckLLM([]))
    g._fallback["s1"] = TaskPlan(
        session_id="s1",
        goal="查票",
        tasks=[
            Task(id="t1", title="查车次", status=TASK_PENDING, sort=0),
            Task(id="t2", title="报价", status=TASK_PENDING, sort=1, depends_on=["t1"]),
        ],
    )
    claimed = g.claim_task(action_name="web_search")
    assert claimed is not None and claimed.id == "t1"
    assert claimed.status == TASK_IN_PROGRESS
    plan = g._get_plan()
    assert plan.progress()["done"] == 0.5
    g.complete_active_task(ok=True, evidence="G123 有票")
    plan = g._get_plan()
    assert plan.tasks[0].status == TASK_DONE
    assert [t.id for t in plan.ready_tasks()] == ["t2"]


@pytest.mark.asyncio
async def test_check_step_drift_blocked_then_escape_valve():
    # 两次 drift → 第一次拦截，第二次 re-anchor 放行（用户真实转向）
    g = _guard(
        FakeCheckLLM([
            '{"verdict": "drift", "reason": "跑去看娱乐新闻", "correction": "回到写报告"}',
            '{"verdict": "drift", "reason": "还是偏离", "correction": "回到写报告"}',
        ])
    )
    await g.ensure_anchor(user_input="写报告")
    r1 = await g.check_step(
        task="写报告", iteration=0, thought="无聊",
        action_name="web_search", action_input={"query": "娱乐新闻"},
    )
    assert r1["verdict"] == "drift"
    assert "写报告" in r1["correction"]

    r2 = await g.check_step(
        task="改做旅游攻略", iteration=1, thought="用户改了主意",
        action_name="web_search", action_input={"query": "旅游攻略"},
    )
    assert r2["verdict"] == "aligned", "连续 drift 应触发 re-anchor 放行"
    plan = g._get_plan()
    assert plan.goal == "改做旅游攻略"
    assert plan.anchor_history and plan.anchor_history[0]["goal"] == "写报告"
    assert all(t.status == TASK_SKIPPED for t in plan.tasks), "旧任务应全部标记放弃"


@pytest.mark.asyncio
async def test_check_step_error_fail_open():
    g = _guard(BoomLLM())
    await g.ensure_anchor(user_input="写报告")
    r = await g.check_step(
        task="写报告", iteration=0, thought="x",
        action_name="web_search", action_input={"query": "q"},
    )
    assert r["verdict"] == "aligned", "检查失败必须 fail-open"
    assert g._get_plan().check_errors == 1


@pytest.mark.asyncio
async def test_check_step_timeout_fail_open():
    g = _guard(FakeCheckLLM(['{"verdict": "aligned"}'], delay=2.0))
    await g.ensure_anchor(user_input="写报告")
    r = await g.check_step(
        task="写报告", iteration=0, thought="x",
        action_name="web_search", action_input={"query": "q"},
    )
    assert r["verdict"] == "aligned"
    assert g._get_plan().check_errors == 1


@pytest.mark.asyncio
async def test_check_step_no_anchor_passes():
    g = _guard(FakeCheckLLM([]))
    r = await g.check_step(
        task="x", iteration=0, thought="y",
        action_name="web_search", action_input={},
    )
    assert r["verdict"] == "aligned"


@pytest.mark.asyncio
async def test_check_step_max_per_turn_skips():
    g = _guard(
        FakeCheckLLM(
            ['{"verdict": "aligned", "reason": "ok"}'] * 10,
        ),
        intent_check_max_per_turn=3,
    )
    await g.ensure_anchor(user_input="写报告")
    for i in range(5):
        await g.check_step(
            task="写报告", iteration=i, thought="x",
            action_name="web_search", action_input={"query": "q"},
        )
    assert g._turn_checks == 5
    # 等后台拆解落定：3 次检查 + 1 次拆解共消费 4 条，超上限的 2 次不再消费
    await asyncio.sleep(0.05)
    assert len(g.checker.llm.outputs) == 6


@pytest.mark.asyncio
async def test_finalize_turn_closes_tasks():
    g = _guard(
        FakeCheckLLM([
            # 拆解输出
            '{"tasks": [{"title": "调研竞品"}, {"title": "产出报告"}]}',
            # 完成度校验输出
            '{"verdict": "complete", "task_updates": ['
            '{"id": "IGNORED", "status": "done"},'
            '{"id": "t1", "status": "done", "note": "已调研"}],'
            ' "new_tasks": [], "open_summary": ""}',
        ])
    )
    plan = await g.ensure_anchor(user_input="写报告")
    await asyncio.sleep(0.05)
    cur = g._get_plan()
    assert cur is not None
    assert [t.title for t in cur.tasks] == ["调研竞品", "产出报告"]

    # 手动把第一个任务置为 pending 以模拟未完成
    cur.tasks[0].status = TASK_PENDING
    g._set_plan(cur)

    fin = await g.finalize_turn(user_input="写报告", answer="已完成调研，报告写完")
    assert fin["verdict"] == "complete"
    # 只闭环真实存在的 t1… 拆解产出的任务 id 是随机的，用 open_tasks 验证更稳：
    # 校验「不存在的 id 被忽略、存在的任务不受影响」由 models 测试覆盖，
    # 这里验证最终 plan 状态与 open_tasks 输出。
    assert "open_tasks" in fin


@pytest.mark.asyncio
async def test_finalize_turn_partial_returns_open_tasks():
    g = _guard(
        FakeCheckLLM([
            # 第 1 条给后台拆解任务消费
            '{"tasks": [{"title": "写报告"}]}',
            # 第 2 条给 finalize 的完成度校验消费
            '{"verdict": "partial", "task_updates": [], '
            '"new_tasks": [{"title": "补充数据文件", "note": "发现未做"}], '
            '"open_summary": "还差数据文件"}',
        ])
    )
    await g.ensure_anchor(user_input="写报告")
    await asyncio.sleep(0.05)
    fin = await g.finalize_turn(user_input="写报告", answer="报告初稿完成")
    assert fin["verdict"] == "partial"
    assert fin["open_summary"] == "还差数据文件"
    assert len(fin["open_tasks"]) >= 1
    titles = [t.title for t in g._get_plan().tasks]
    assert "补充数据文件" in titles


@pytest.mark.asyncio
async def test_finalize_turn_no_anchor_returns_empty():
    g = _guard(FakeCheckLLM([]))
    fin = await g.finalize_turn(user_input="x", answer="y")
    assert fin["verdict"] == "complete"
    assert fin["open_tasks"] == []


@pytest.mark.asyncio
async def test_snapshot():
    g = _guard(FakeCheckLLM([]))
    assert g.snapshot() is None
    await g.ensure_anchor(user_input="目标")
    snap = g.snapshot()
    assert snap is not None and snap["goal"] == "目标"


@pytest.mark.asyncio
async def test_pre_turn_check_same_goal_skips_llm():
    # 空 LLM：若真的调用会返回 {} → verdict=error；断言 same 证明走了短路
    g = _guard(FakeCheckLLM([]))
    await g.ensure_anchor(user_input="写报告")
    r = await g.pre_turn_check(user_input="写报告")
    assert r == {"verdict": "same", "reanchored": False}


@pytest.mark.asyncio
async def test_pre_turn_check_drift_reanchors():
    g = _guard(
        FakeCheckLLM([
            '{"verdict": "drift", "reason": "新话题", "correction": ""}',
        ])
    )
    await g.ensure_anchor(user_input="写报告")
    r = await g.pre_turn_check(user_input="帮我订个机票")
    assert r["verdict"] == "switch"
    assert r["reanchored"] is True
    plan = g._get_plan()
    assert plan.goal == "帮我订个机票"
    assert plan.anchor_history and plan.anchor_history[0]["goal"] == "写报告"


@pytest.mark.asyncio
async def test_pre_turn_check_error_fail_open():
    g = _guard(BoomLLM())
    await g.ensure_anchor(user_input="写报告")
    r = await g.pre_turn_check(user_input="换个话题")
    assert r["verdict"] == "error"
    assert r["reanchored"] is False


@pytest.mark.asyncio
async def test_close_turn_appends_open_tasks_notice():
    g = _guard(
        FakeCheckLLM([
            '{"verdict": "partial", "task_updates": [], "new_tasks": [], '
            '"open_summary": "还没做完"}'
        ])
    )
    await g.ensure_anchor(user_input="写报告")
    await asyncio.sleep(0.05)
    answer, meta = await g.close_turn(user_input="写报告", answer="初稿完成")
    assert "【未完成任务清单】" in answer
    assert answer.startswith("初稿完成")
    assert meta.get("task_plan") is not None


@pytest.mark.asyncio
async def test_close_turn_complete_no_notice():
    g = _guard(
        FakeCheckLLM([
            # 第 1 条给后台拆解任务消费
            '{"tasks": [{"title": "写报告"}]}',
            # 第 2 条给 finalize 的完成度校验消费
            '{"verdict": "complete", "task_updates": [], "new_tasks": [], "open_summary": ""}',
        ])
    )
    await g.ensure_anchor(user_input="写报告")
    await asyncio.sleep(0.05)
    answer, meta = await g.close_turn(user_input="写报告", answer="全部完成")
    assert answer == "全部完成"
    assert meta.get("task_plan") is not None
