"""Intent Guard 数据模型与 JSON 容错解析单测。"""

from __future__ import annotations

from intent.checker import parse_json_lenient
from intent.models import (
    TASK_BLOCKED,
    TASK_DONE,
    TASK_IN_PROGRESS,
    TASK_PENDING,
    TASK_SKIPPED,
    Task,
    TaskPlan,
)


def _plan() -> TaskPlan:
    p = TaskPlan(session_id="s1", goal="写一份竞品分析报告")
    p.tasks = [
        Task(id="t1", title="调研竞品定价", status=TASK_DONE, closed_by="check", sort=0),
        Task(id="t2", title="产出报告正文", status=TASK_IN_PROGRESS, sort=1),
        Task(id="t3", title="给出定价建议", status=TASK_PENDING, sort=2),
        Task(id="t4", title="旧任务", status=TASK_SKIPPED, sort=3),
    ]
    return p


def test_taskplan_roundtrip():
    p = _plan()
    p.version = 5
    p.drift_count = 2
    p.blocked_actions = 1
    p.anchor_history = [{"goal": "旧目标", "reason": "用户转向"}]
    p.last_check = {"verdict": "drift", "reason": "偏了"}
    restored = TaskPlan.from_dict(p.to_dict())
    assert restored.goal == "写一份竞品分析报告"
    assert restored.version == 5
    assert restored.drift_count == 2
    assert [t.id for t in restored.tasks] == ["t1", "t2", "t3", "t4"]
    assert restored.tasks[0].status == TASK_DONE
    assert restored.tasks[0].closed_by == "check"
    assert restored.anchor_history[0]["goal"] == "旧目标"
    assert restored.last_check["verdict"] == "drift"


def test_taskplan_progress_excludes_skipped():
    p = _plan()
    # t1 done=1，t2 in_progress=0.5，t3 pending=0，t4 skipped 不计
    assert p.progress() == {"done": 1.5, "total": 3.0}


def test_ready_tasks_respects_depends_on():
    p = TaskPlan(session_id="s1", goal="查票")
    p.tasks = [
        Task(id="t1", title="查车次", status=TASK_PENDING, sort=0),
        Task(id="t2", title="报价", status=TASK_PENDING, sort=1, depends_on=["t1"]),
    ]
    assert [t.id for t in p.ready_tasks()] == ["t1"]
    p.tasks[0].status = TASK_DONE
    assert [t.id for t in p.ready_tasks()] == ["t2"]


def test_taskplan_open_tasks():
    p = _plan()
    assert [t.id for t in p.open_tasks()] == ["t2", "t3"]


def test_task_invalid_status_falls_back_to_pending():
    t = Task.from_dict({"id": "x", "title": "y", "status": "weird"})
    assert t.status == TASK_PENDING


def test_taskplan_from_empty_dict():
    p = TaskPlan.from_dict({})
    assert p.goal == ""
    assert p.tasks == []
    assert p.version == 0


def test_parse_json_plain():
    assert parse_json_lenient('{"verdict": "aligned"}')["verdict"] == "aligned"


def test_parse_json_fenced():
    raw = '```json\n{"verdict": "drift"}\n```'
    assert parse_json_lenient(raw)["verdict"] == "drift"


def test_parse_json_with_prose_around():
    raw = '判断结果：{"verdict": "irrelevant", "reason": "闲聊"} 完毕'
    assert parse_json_lenient(raw)["verdict"] == "irrelevant"


def test_parse_json_garbage():
    assert parse_json_lenient("完全不是 JSON") == {}
    assert parse_json_lenient("") == {}


def test_human_text():
    p = _plan()
    text = p.human_text()
    assert "竞品分析报告" in text
    assert "进行中" in text
