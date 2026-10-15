"""评测加载器冒烟：不调 LLM，只验证 YAML → EvalCase。"""

from __future__ import annotations

from .eval_loader import load_suite
from .eval_runner import check_expect_text, match_tools, strip_open_tasks_footer
from .eval_schema import EvalCase, EvalExpect


def test_load_p0_suite_has_core_cases():
    cases = load_suite(tags_any={"p0"})
    ids = {c.id for c in cases}
    assert "chat_http_one_liner" in ids
    assert "agent_need_web_search" in ids
    assert "security_blocked_keyword" in ids
    for c in cases:
        if c.id == "chat_http_one_liner":
            assert c.pass_mode == "pass_hat_k"
            assert c.k >= 1


def test_match_tools_subset():
    ok, _ = match_tools(["web_search", "calculator"], ["web_search"], "subset")
    assert ok
    ok2, _ = match_tools(["calculator"], ["web_search"], "subset")
    assert not ok2


def test_match_tools_empty_strict_means_zero_tools():
    ok, _ = match_tools([], [], "strict")
    assert ok
    ok2, _ = match_tools(["web_search"], [], "strict")
    assert not ok2
    # subset + 空期望：无约束（兼容旧题）
    ok3, _ = match_tools(["web_search"], [], "subset")
    assert ok3


def test_check_max_tool_calls():
    from .eval_runner import check_max_tool_calls

    ok, _ = check_max_tool_calls(["web_search"], 1)
    assert ok
    ok2, _ = check_max_tool_calls(["web_search", "web_search"], 1)
    assert not ok2
    ok3, _ = check_max_tool_calls(["a", "b"], None)
    assert ok3


def test_load_hard_suite():
    cases = load_suite(tags_any={"hard"})
    ids = {c.id for c in cases}
    assert "agent_greeting_no_tools" in ids
    assert "agent_search_budget" in ids
    assert "chat_contradict_then_ask" in ids
    assert "security_obfuscated_jailbreak" in ids
    budget = next(c for c in cases if c.id == "agent_search_budget")
    assert budget.trajectory.max_tool_calls == 1
    greet = next(c for c in cases if c.id == "agent_greeting_no_tools")
    assert greet.trajectory.match_mode == "strict"
    assert greet.trajectory.expected_tools == []


def test_strip_open_tasks_footer():
    raw = "一句答案。\n\n---\n【未完成任务清单】\n1. 某任务（待办）"
    assert strip_open_tasks_footer(raw) == "一句答案。"
    assert strip_open_tasks_footer("干净答案") == "干净答案"


def test_check_expect_any():
    case = EvalCase(
        id="t",
        expect=EvalExpect(
            must_contain=["安全拦截", "prompt injection"],
            match_any_of_must_contain=True,
        ),
    )
    ok, _ = check_expect_text("[安全拦截] 检测到潜在的 prompt injection 攻击", case)
    assert ok
