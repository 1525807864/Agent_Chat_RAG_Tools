"""ReActAgent × IntentGuard 集成测：drift 拦截 / 放行 / guard 缺失行为不变。"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage
from langchain_core.tools import tool

from agents.react_agent import ReActAgent

# ------------------------------------------------------------------ 假件


@tool
def fake_search(query: str) -> str:
    """假搜索工具。"""
    calls.append(query)
    return f"搜索结果: {query}"


calls: list[str] = []


class SeqLLM:
    """按顺序返回预设 ReAct 文本。"""

    def __init__(self, responses: list[str]):
        self.responses = list(responses)
        self.model_name = "fake-main-model"

    async def ainvoke(self, messages, **kwargs):
        if not self.responses:
            return AIMessage(content="Final Answer: 无内容")
        return AIMessage(content=self.responses.pop(0))


class DriftOnceGuard:
    """第一次 drift，之后 aligned 的假守卫（鸭子类型）。"""

    def __init__(self):
        self.calls = 0

    async def check_step(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            return {
                "verdict": "drift",
                "reason": "偏离目标",
                "correction": "回到写报告",
            }
        return {"verdict": "aligned", "reason": "ok"}


class AlignedGuard:
    async def check_step(self, **kwargs):
        return {"verdict": "aligned", "reason": "ok"}


def _agent(llm, max_tool_calls: int = 5) -> ReActAgent:
    return ReActAgent(
        name="t",
        role="测试",
        llm=llm,
        tools=[fake_search],
        max_tool_calls=max_tool_calls,
    )


# ------------------------------------------------------------------ 用例


@pytest.mark.asyncio
async def test_drift_step_is_blocked_and_reminded():
    calls.clear()
    llm = SeqLLM(
        [
            # 第 1 轮：想搜索 → 被 guard 拦截（drift）
            'Thought: 搜点无关的\nAction: fake_search\nAction Input: {"query": "娱乐"}\n',
            # 第 2 轮：被提醒后回到正轨 → aligned 放行
            'Thought: 回到正轨\nAction: fake_search\nAction Input: {"query": "竞品"}\n',
            "Final Answer: 完成",
        ]
    )
    agent = _agent(llm)
    result = await agent.run("写竞品报告", {"intent_guard": DriftOnceGuard()})
    assert result["result"] == "完成"
    assert calls == ["竞品"], "drift 的工具调用不应执行"
    blocked = [c for c in result["tool_calls"] if c.get("blocked_by_intent")]
    assert len(blocked) == 1
    assert blocked[0]["tool"] == "fake_search"
    assert "写报告" in blocked[0]["correction"]


@pytest.mark.asyncio
async def test_aligned_guard_does_not_block():
    calls.clear()
    llm = SeqLLM(
        [
            'Thought: 查资料\nAction: fake_search\nAction Input: {"query": "x"}\n',
            "Final Answer: 好了",
        ]
    )
    agent = _agent(llm)
    result = await agent.run("任务", {"intent_guard": AlignedGuard()})
    assert result["result"] == "好了"
    assert calls == ["x"]
    assert not any(c.get("blocked_by_intent") for c in result["tool_calls"])


@pytest.mark.asyncio
async def test_no_guard_behaves_as_before():
    calls.clear()
    llm = SeqLLM(
        [
            'Thought: 查资料\nAction: fake_search\nAction Input: {"query": "x"}\n',
            "Final Answer: 好了",
        ]
    )
    agent = _agent(llm)
    result = await agent.run("任务", {"history": []})
    assert result["result"] == "好了"
    assert calls == ["x"]
    assert result["tool_calls"][0]["tool"] == "fake_search"
