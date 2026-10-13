# ============================================================================
# test_deepeval_chat_modes.py
# DeepEval + GEval：覆盖 chat / rag / agent / multi 主路径
#
# 运行（仓库根目录，需 .env 里 DEEPSEEK_API_KEY）：
#   $env:PYTHONIOENCODING="utf-8"
#   pytest tests/power_test/test_deepeval_chat_modes.py -v -s
# ============================================================================

from __future__ import annotations

import pytest
from deepeval.metrics import AnswerRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from .deepeval_harness import (
    DeepSeekJudge,
    clip,
    get_app,
    make_geval,
    measure_ok,
    new_session,
    sources_to_contexts,
)


@pytest.mark.asyncio
async def test_chat_geval_correctness():
    """【chat】普通对话：GEval 评「是否正确、简洁回答问题」。"""
    app = await get_app()  # 初始化被测应用
    q = "用一句话解释什么是 HTTP"  # 输入问题
    sid = new_session("chat")  # 新会话，避免污染
    result = await app.use_cases.chat.execute(
        q, session_id=sid, tenant_id="default"
    )
    actual = clip(result.answer or "")  # 截断后再交给裁判
    assert actual, "chat 返回空"

    metric = make_geval(
        name="ChatCorrectness",
        criteria=(
            "评估回答是否准确解释了 HTTP 的基本含义，"
            "是否简洁、无胡编乱造。满分需切题且无严重事实错误。"
        ),
        threshold=0.6,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
    )
    case = LLMTestCase(input=q, actual_output=actual)
    await measure_ok(metric, case)


@pytest.mark.asyncio
async def test_chat_memory_geval():
    """【chat 记忆】同 session 两轮：第二轮是否用到第一轮信息。"""
    app = await get_app()
    sid = new_session("mem")
    # 第一轮：写入记忆
    await app.use_cases.chat.execute(
        "我的名字叫小明，请记住。",
        session_id=sid,
        tenant_id="default",
    )
    # 第二轮：考记忆
    q2 = "我叫什么名字？"
    r2 = await app.use_cases.chat.execute(
        q2, session_id=sid, tenant_id="default"
    )
    actual = clip(r2.answer or "")
    assert actual, "第二轮空回答"

    metric = make_geval(
        name="MemoryRecall",
        criteria=(
            "用户第一轮说自己叫小明；第二轮问名字时，"
            "回答应明确提到小明或等价指代。未体现记忆则低分。"
        ),
        threshold=0.55,
    )
    case = LLMTestCase(input=q2, actual_output=actual)
    await measure_ok(metric, case)


@pytest.mark.asyncio
async def test_rag_faithfulness_and_geval():
    """【rag】混合检索：AnswerRelevancy +（有 sources 时）Faithfulness + GEval。

    若本机未建知识库，sources 可能为空：跳过 Faithfulness，仍评相关性与有用性。
    """
    app = await get_app()
    q = "根据知识库，简要说明本项目的主要功能"
    sid = new_session("rag")
    result = await app.use_cases.rag.execute(
        q, session_id=sid, tenant_id="default"
    )
    actual = clip(result.answer or "")
    assert actual, "rag 空回答"

    contexts = sources_to_contexts(result)  # meta.sources → 文本列表
    judge = DeepSeekJudge()

    # 1) 回答是否相关
    rel = AnswerRelevancyMetric(
        threshold=0.5,
        model=judge,
        include_reason=True,
        async_mode=True,
    )
    case = LLMTestCase(
        input=q,
        actual_output=actual,
        retrieval_context=contexts or None,
    )
    await measure_ok(rel, case)

    # 2) 有检索片段才测 Faithfulness（无库时不必硬 fail）
    if contexts:
        faith = FaithfulnessMetric(
            threshold=0.5,
            model=judge,
            include_reason=True,
            async_mode=True,
        )
        await measure_ok(faith, case)
    else:
        print("[rag] 无 sources，跳过 Faithfulness（请先对本租户建库）")

    # 3) GEval：有用性 / 不胡编
    ge = make_geval(
        name="RagUsefulness",
        criteria=(
            "回答应紧扣问题；若有检索内容应尽量依据材料，"
            "不胡编关键接口或功能。"
        ),
        threshold=0.55,
    )
    await measure_ok(ge, case)


@pytest.mark.asyncio
async def test_agent_relevancy_geval():
    """【agent】工具环：AnswerRelevancy + GEval（工具正确性见 tool_calling 文件）。"""
    app = await get_app()
    q = "什么是人工智能"
    sid = new_session("agent")
    result = await app.use_cases.agent.execute(
        q,
        session_id=sid,
        tenant_id="default",
        agent_name="assistant",
    )
    actual = clip(result.answer or "")
    assert actual, "agent 空回答"

    judge = DeepSeekJudge()
    rel = AnswerRelevancyMetric(
        threshold=0.5,
        model=judge,
        include_reason=True,
        async_mode=True,
    )
    case = LLMTestCase(input=q, actual_output=actual)
    await measure_ok(rel, case)

    ge = make_geval(
        name="AgentQuality",
        criteria="回答应切题、可读；允许简短；不应答非所问。",
        threshold=0.55,
    )
    await measure_ok(ge, case)


@pytest.mark.asyncio
async def test_multi_geval():
    """【multi】多智能体 sequential：GEval 评最终综合质量。"""
    app = await get_app()
    q = "请用三点概括单元测试的好处"
    sid = new_session("multi")
    result = await app.use_cases.multi.execute(
        q,
        session_id=sid,
        tenant_id="default",
        multi_mode="sequential",  # 与 MultiAgentUseCase 签名一致
    )
    actual = clip(result.answer or "")
    assert actual, "multi 空回答"

    ge = make_geval(
        name="MultiSummary",
        criteria=(
            "最终回答应给出与单元测试相关的若干要点，结构清晰；"
            "不应与问题无关。"
        ),
        threshold=0.55,
    )
    case = LLMTestCase(input=q, actual_output=actual)
    await measure_ok(ge, case)
