"""DeepEval：工具调用能力评测（ToolCallingAgent / 也可改成 ReAct）。

测什么
======
1. 模型是否调用了「期望的工具」（ToolCorrectness）
2. 最终自然语言回答是否和问题相关（AnswerRelevancy，可选）
3. 硬断言：trace 里确实出现过工具名（不花裁判费，先做冒烟）

运行（仓库根目录，需 .env 里 DEEPSEEK_API_KEY）
============================================
  $env:PYTHONIOENCODING="utf-8"
  pytest tests/power_test/test_deepeval_tool_calling.py -v -s

说明
====
- 不用 assert_test（Windows GBK + rich 进度条易炸），用 metric.a_measure
- 裁判默认 deepseek-chat + json_object（与 test_deepeval_agent_min 一致）
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

# ---------- 路径 / 编码 / 默认后端（与现有 DeepEval 最小用例一致）----------
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 单测不要误连 Docker 主机名
os.environ.setdefault("AUTH_BACKEND", "sqlite")
os.environ.setdefault("MEMORY_BACKEND", "sqlite")

import pytest
from deepeval.metrics import AnswerRelevancyMetric, ToolCorrectnessMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase, ToolCall


# =============================================================================
# 裁判模型：DeepSeek（给 DeepEval 打分用，不是被测 Agent）
# =============================================================================

def _extract_text(message: object) -> str:
    """兼容 deepseek-v4：content 为空时尝试 reasoning_content。"""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    if isinstance(message, dict):
        for key in ("content", "reasoning_content"):
            val = message.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


class DeepSeekJudge(DeepEvalBaseLLM):
    """DeepEval 裁判：OpenAI 兼容 API → DeepSeek。"""

    def __init__(self) -> None:
        from openai import OpenAI, AsyncOpenAI
        from config.settings import get_settings

        s = get_settings()
        # 裁判用 chat 更稳；可用环境变量覆盖
        self._model = os.getenv("DEEPEVAL_JUDGE_MODEL") or "deepseek-chat"
        self._max_tokens = max(int(s.model_max_tokens or 8192), 8192)
        api_key = s.deepseek_api_key or ""
        base_url = s.deepseek_api_base or "https://api.deepseek.com/v1"
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0)
        self._aclient = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=180.0)

    def load_model(self):
        return self._client

    def _create_kwargs(self, prompt: str) -> dict:
        return {
            "model": self._model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are an evaluation assistant. "
                        "Reply with valid JSON only, no markdown fences."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0,
            "max_tokens": self._max_tokens,
        }

    def generate(self, prompt: str) -> str:
        kwargs = self._create_kwargs(prompt)
        try:
            resp = self._client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception:
            resp = self._client.chat.completions.create(**kwargs)
        text = _extract_text(resp.choices[0].message)
        if not text.strip():
            raise ValueError("Judge 返回空内容")
        return text

    async def a_generate(self, prompt: str) -> str:
        kwargs = self._create_kwargs(prompt)
        try:
            resp = await self._aclient.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}
            )
        except Exception:
            resp = await self._aclient.chat.completions.create(**kwargs)
        text = _extract_text(resp.choices[0].message)
        if not text.strip():
            raise ValueError("Judge 返回空内容")
        return text

    def get_model_name(self) -> str:
        return str(self._model)


# =============================================================================
# 被测对象：组装 ToolCallingAgent + 本地工具（calculator / web_search …）
# =============================================================================

async def _run_tool_calling_agent(task: str) -> dict:
    """跑一轮原生 tool calling，返回 {result, trace, usage, tools_called}。

    tools_called：转成 DeepEval ToolCall 列表，供 ToolCorrectnessMetric 使用。
    """
    from agents.tool_calling_agent import ToolCallingAgent
    from agents.tools_registry import create_default_registry
    from application.tools.gateway import ToolGateway
    from infrastructure.llm.openai_compat import create_chat_openai
    from config.settings import get_settings

    s = get_settings()
    assert s.deepseek_api_key, "缺少 DEEPSEEK_API_KEY，无法跑真实 tool calling"

    # 被测 LLM：用你项目日常模型（可用环境变量单独指定）
    llm = create_chat_openai(
        api_key=s.deepseek_api_key or "",
        api_base=s.deepseek_api_base or "",
        model=os.getenv("DEEPEVAL_AGENT_MODEL") or s.model_name,
        temperature=0,  # 评测尽量稳
        max_tokens=s.model_max_tokens,
        streaming=False,
    )

    registry = create_default_registry(
        allowed_roots=s.allowed_data_roots,
        project_root=_ROOT,
        enable_execute_python=False,  # 评测关掉危险工具
    )
    gateway = ToolGateway(
        registry,
        mcp_servers_json="",           # 评测先不挂 MCP，减少不稳定因素
        active_tool_discovery=False,
        logger=None,
    )

    system_prompt = (
        "你是助手。需要计算时用 calculator；需要联网事实时用 web_search。"
        "工具返回后再用中文给出最终答案。不要编造 Observation。"
    )

    async with gateway.open_act_session() as assembled:
        agent = ToolCallingAgent(
            name="tool_eval",
            llm=llm,
            tools=list(assembled.tools),
            system_prompt=system_prompt,
            max_rounds=6,
            role="评测助手",
        )
        raw = await agent.run(task)

    # ---- 从 trace 抽出「实际调用过的工具」→ DeepEval ToolCall ----
    # ToolCallingAgent.trace 元素形如：
    #   {"type":"tool", "name":"calculator", "args":{...}, "output":"..."}
    tools_called: list[ToolCall] = []
    for step in raw.get("trace") or []:
        if step.get("type") != "tool":
            continue
        if step.get("blocked_by_intent"):
            continue  # 被意图守卫拦截的不算「成功调用」
        name = (step.get("name") or "").strip()
        if not name:
            continue
        args = step.get("args") or {}
        if not isinstance(args, dict):
            args = {"_raw": str(args)}
        tools_called.append(
            ToolCall(
                name=name,
                # DeepEval 字段名：input_parameters
                input_parameters=args,
            )
        )

    return {
        "result": (raw.get("result") or "").strip(),
        "trace": raw.get("trace") or [],
        "usage": raw.get("usage") or {},
        "tools_called": tools_called,
        # 方便硬断言：纯名字列表
        "tool_names": [t.name for t in tools_called],
    }


# =============================================================================
# 用例 1：计算题 —— 期望调用 calculator
# =============================================================================

@pytest.mark.asyncio
async def test_tool_calling_calculator_correctness():
    """问算术题 → 应调用 calculator；用 ToolCorrectness 打分。"""
    question = "请用工具计算：(12 + 30) * 2 等于多少？只给最终数字即可。"

    # ---------- 1) 跑被测 Agent ----------
    out = await _run_tool_calling_agent(question)
    actual = out["result"]
    tools_called = out["tools_called"]

    print("\n[实际回答]", actual[:500])
    print("[实际工具]", out["tool_names"])
    print("[usage]", out["usage"])

    # ---------- 2) 便宜的硬断言（裁判失败时也能先暴露问题）----------
    assert actual, "Agent 返回空答案"
    assert "calculator" in out["tool_names"], (
        f"期望调用 calculator，实际={out['tool_names']} trace={out['trace']}"
    )

    # ---------- 3) DeepEval ToolCorrectness ----------
    # expected_tools：你「认为正确」的工具调用（可只写 name，或连参数一起写严一点）
    expected_tools = [
        ToolCall(
            name="calculator",
            # 参数名以你 registry 里 calculator(expression=...) 为准
            input_parameters={"expression": "(12 + 30) * 2"},
        )
    ]
    # 若模型表达式写法不唯一（如 "12+30*2"），可先只比工具名：
    #   expected_tools = [ToolCall(name="calculator")]
    # 并看当前 deepeval 版本是否支持 should_exact_match / 忽略参数。

    case = LLMTestCase(
        input=question,
        actual_output=actual,
        tools_called=tools_called,       # Agent 真实调用
        expected_tools=expected_tools,   # 你定义的期望
    )

    judge = DeepSeekJudge()
    metric = ToolCorrectnessMetric(
        threshold=0.5,          # 按需要调高（如 0.7）
        model=judge,            # 部分版本 ToolCorrectness 主要靠匹配，可不依赖 LLM
        include_reason=True,
    )

    # 同步/异步以你安装的 deepeval 为准；优先 a_measure，没有就 measure
    if hasattr(metric, "a_measure"):
        score = await metric.a_measure(case)
    else:
        score = metric.measure(case)

    print(f"[ToolCorrectness] score={score} reason={getattr(metric, 'reason', '')}")
    assert metric.is_successful(), (
        f"工具调用不正确: score={score}, reason={getattr(metric, 'reason', None)}, "
        f"called={out['tool_names']}"
    )


# =============================================================================
# 用例 2：需要联网 —— 期望调用 web_search（可再加 Relevancy）
# =============================================================================

@pytest.mark.asyncio
async def test_tool_calling_web_search_and_relevancy():
    """时效/事实题 → 应 web_search；答案用 AnswerRelevancy 再评一层。"""
    question = "用工具查一下：今天北京大概天气怎么样？用中文简要回答。"

    out = await _run_tool_calling_agent(question)
    actual = out["result"]
    tools_called = out["tools_called"]

    print("\n[实际回答]", actual[:500])
    print("[实际工具]", out["tool_names"])

    assert actual, "空答案"
    assert "web_search" in out["tool_names"], (
        f"期望 web_search，实际={out['tool_names']}"
    )

    # ---- ToolCorrectness：至少要有 web_search ----
    case_tool = LLMTestCase(
        input=question,
        actual_output=actual,
        tools_called=tools_called,
        expected_tools=[ToolCall(name="web_search")],
    )
    judge = DeepSeekJudge()
    tool_metric = ToolCorrectnessMetric(
        threshold=0.5, 
        model = judge,
        include_reason=True)
    if hasattr(tool_metric, "a_measure"):
        await tool_metric.a_measure(case_tool)
    else:
        tool_metric.measure(case_tool)
    assert tool_metric.is_successful(), tool_metric.reason

    # ---- AnswerRelevancy：最终话是否答到点上（截断防 JSON 爆）----
    eval_output = actual if len(actual) <= 1200 else actual[:1200] + "…"
    case_ans = LLMTestCase(input=question, actual_output=eval_output)
    judge = DeepSeekJudge()
    ans_metric = AnswerRelevancyMetric(
        threshold=0.5,
        model=judge,
        include_reason=True,
        async_mode=True,
    )
    score = await ans_metric.a_measure(case_ans)
    print(f"[AnswerRelevancy] score={score} reason={ans_metric.reason}")
    assert ans_metric.is_successful(), ans_metric.reason


# =============================================================================
# 用例 3（可选）：不该调工具 —— 问候语
# =============================================================================

@pytest.mark.asyncio
async def test_tool_calling_should_not_call_tools():
    """纯问候不应乱调工具（硬断言；DeepEval 也可 expected_tools=[]）。"""
    question = "你好，请用一句话介绍你自己。"

    out = await _run_tool_calling_agent(question)
    print("\n[实际回答]", out["result"][:300])
    print("[实际工具]", out["tool_names"])

    assert out["result"], "空答案"
    # 策略：问候题tool_names 应为空（若你们 prompt 强制搜索，这条会失败，属预期）
    assert out["tool_names"] == [], (
        f"问候题不应调工具，实际调用了: {out['tool_names']}"
    )

    case = LLMTestCase(
        input=question,
        actual_output=out["result"],
        tools_called=out["tools_called"],
        expected_tools=[],  # 期望零工具
    )
    judge = DeepSeekJudge()
    metric = ToolCorrectnessMetric(threshold=0.5, model=judge,include_reason=True)
    if hasattr(metric, "a_measure"):
        await metric.a_measure(case)
    else:
        metric.measure(case)
    assert metric.is_successful(), metric.reason