"""最小 DeepEval：真实调用本项目 Agent + DeepSeek 裁判。

运行（仓库根目录，需 .env 里 DEEPSEEK_API_KEY）：
  $env:PYTHONPATH="d:\\LangChain_Demo"
  $env:PYTHONIOENCODING="utf-8"
  pytest tests/power_test/test_deepeval_agent_min.py -v -s
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 保证仓库根在 sys.path（不依赖手动 PYTHONPATH）
_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Windows 控制台避免 DeepEval / rich emoji 触发 GBK 编码错误
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# 单测默认 sqlite，避免误连 Docker 主机名 mysql
os.environ.setdefault("AUTH_BACKEND", "sqlite")
os.environ.setdefault("MEMORY_BACKEND", "sqlite")

import pytest
from deepeval.metrics import AnswerRelevancyMetric
from deepeval.models import DeepEvalBaseLLM
from deepeval.test_case import LLMTestCase


def _extract_text(message: object) -> str:
    """兼容 deepseek-v4：content 为空时尝试 reasoning_content。"""
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    reasoning = getattr(message, "reasoning_content", None)
    if isinstance(reasoning, str) and reasoning.strip():
        return reasoning
    # dict 形态
    if isinstance(message, dict):
        for key in ("content", "reasoning_content"):
            val = message.get(key)
            if isinstance(val, str) and val.strip():
                return val
    return ""


class DeepSeekJudge(DeepEvalBaseLLM):
    """DeepEval 裁判：直连 DeepSeek OpenAI 兼容 API（给足 max_tokens）。"""

    def __init__(self) -> None:
        from openai import OpenAI, AsyncOpenAI
        from config.settings import get_settings

        s = get_settings()
        # 裁判优先用 deepseek-chat：结构化 JSON 更稳；v4-flash 易截断/空 content
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
            raise ValueError(
                f"Judge 返回空内容 finish_reason="
                f"{getattr(resp.choices[0], 'finish_reason', None)}"
            )
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
            raise ValueError(
                f"Judge 返回空内容 finish_reason="
                f"{getattr(resp.choices[0], 'finish_reason', None)}"
            )
        return text

    def get_model_name(self) -> str:
        return str(self._model)


@pytest.mark.asyncio
async def test_agent_answer_relevancy_real_api():
    """真实 Agent：问「什么是人工智能」，用 DeepEval 测回答相关性。"""
    from application.services.agent_application import AgentApplication

    question = "什么是人工智能"
    app = AgentApplication()
    if app.memory is None:
        await app.init_session_store()

    # 每次新会话，避免「重复提问」污染回答（拉低 Relevancy）
    import uuid

    session_id = f"deepeval__min_{uuid.uuid4().hex[:8]}"
    result = await app.use_cases.agent.execute(
        question,
        session_id=session_id,
        tenant_id="default",
        agent_name="assistant",
    )
    actual = (result.answer or "").strip()
    assert actual, "Agent 返回空答案"
    print(f"\n[Agent 回答预览]\n{actual[:500]}\n")

    # AnswerRelevancy 会把答案拆成 statements；过长易让裁判 JSON 截断
    eval_output = actual if len(actual) <= 1200 else actual[:1200] + "…"

    judge = DeepSeekJudge()
    metric = AnswerRelevancyMetric(
        threshold=0.5,
        model=judge,
        include_reason=True,
        async_mode=True,
    )
    case = LLMTestCase(input=question, actual_output=eval_output)

    # 不用 assert_test（rich 进度条在 GBK 控制台会炸），直接 measure
    score = await metric.a_measure(case)
    print(f"[DeepEval] score={score} threshold={metric.threshold}")
    print(f"[DeepEval] reason={metric.reason}")
    assert metric.is_successful(), (
        f"AnswerRelevancy 未通过: score={score}, reason={metric.reason}"
    )
