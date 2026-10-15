# ============================================================================
# deepeval_harness.py
# DeepEval 公共脚手架：路径 / 编码 / DeepSeek 裁判 / GEval 工厂 / 跑被测 App
# 所有 power_test 用例共用，避免每个文件复制一份 Judge
# ============================================================================

from __future__ import annotations  # 允许前向注解

import os  # 环境变量 / 默认后端
import sys  # sys.path、stdout 编码
import uuid  # 唯一 session_id
from pathlib import Path  # 仓库根路径

# ---------- 仓库根加入 path（不依赖手动 PYTHONPATH）----------
_ROOT = Path(__file__).resolve().parents[2]  # tests/power_test → 仓库根
if str(_ROOT) not in sys.path:  # 尚未加入
    sys.path.insert(0, str(_ROOT))  # 插到最前

# ---------- Windows：避免 DeepEval / rich emoji 触发 GBK ----------
os.environ.setdefault("PYTHONIOENCODING", "utf-8")  # 子进程也尽量 UTF-8
if hasattr(sys.stdout, "reconfigure"):  # 新版 Python 可重配编码
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # 标准输出
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # 错误输出
    except Exception:  # 个别环境不允许
        pass  # 忽略

# ---------- 单测默认 sqlite，避免误连 Docker 主机名 mysql ----------
os.environ.setdefault("AUTH_BACKEND", "sqlite")  # 鉴权本地库
os.environ.setdefault("MEMORY_BACKEND", "sqlite")  # 会话本地库

# ---------- 新版 deepeval 只接受 CONFIDENT_REGION=EU|US ----------
# .env.local 若写 CN，deepeval Settings 会 ValidationError；本地裁判不依赖该区
os.environ["CONFIDENT_REGION"] = "US"  # 强制合法值（仅本进程）

from deepeval.models import DeepEvalBaseLLM  # 裁判基类（env 修好后再 import）


def _extract_text(message: object) -> str:
    """从 ChatCompletion message 抽文本；兼容 content 空但有 reasoning_content。"""
    content = getattr(message, "content", None)  # 常规字段
    if isinstance(content, str) and content.strip():  # 有正文
        return content  # 直接用
    reasoning = getattr(message, "reasoning_content", None)  # 部分模型推理字段
    if isinstance(reasoning, str) and reasoning.strip():  # 有推理文本
        return reasoning  # 退而用之
    if isinstance(message, dict):  # dict 形态兜底
        for key in ("content", "reasoning_content"):  # 依次试
            val = message.get(key)  # 取值
            if isinstance(val, str) and val.strip():  # 非空字符串
                return val  # 返回
    return ""  # 实在没有就空串


class DeepSeekJudge(DeepEvalBaseLLM):
    """DeepEval 裁判 LLM：打分用，不是被测 Agent。

    与 test_deepeval_agent_min.py 保持一致：正常继承 DeepEvalBaseLLM，
    直连 DeepSeek OpenAI 兼容 API。
    """

    def __init__(self) -> None:
        from openai import AsyncOpenAI, OpenAI  # OpenAI 兼容客户端
        from config.settings import get_settings  # 读 .env

        s = get_settings()  # 加载配置
        # 裁判模型：结构化 JSON 更稳；可用环境变量覆盖
        self._model = os.getenv("DEEPEVAL_JUDGE_MODEL") or "deepseek-chat"
        self._max_tokens = max(int(s.model_max_tokens or 8192), 8192)  # 防截断
        api_key = s.deepseek_api_key or ""  # Key
        base_url = s.deepseek_api_base or "https://api.deepseek.com/v1"  # Base
        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=180.0)
        self._aclient = AsyncOpenAI(api_key=api_key, base_url=base_url, timeout=180.0)

    def load_model(self):
        """DeepEval 要求：返回底层 client。"""
        return self._client

    def _create_kwargs(self, prompt: str) -> dict:
        """组装 chat.completions 参数。"""
        return {
            "model": self._model,  # 裁判模型名
            "messages": [
                {
                    "role": "system",
                    "content": (
                        # DeepEval 会把评分 schema 放进 user prompt；
                        # system 只需强调「只输出合法 JSON」
                        "You are an evaluation assistant. "
                        "Reply with valid JSON only, no markdown fences."
                    ),
                },
                {"role": "user", "content": prompt},  # DeepEval 拼好的评分 prompt
            ],
            "temperature": 0,  # 评分要稳定
            "max_tokens": self._max_tokens,  # 足够长，避免 JSON 半截
        }

    def generate(self, prompt: str) -> str:
        """同步生成（DeepEval 同步路径会调）。"""
        kwargs = self._create_kwargs(prompt)
        try:
            resp = self._client.chat.completions.create(
                **kwargs, response_format={"type": "json_object"}  # 强制 JSON
            )
        except Exception:
            resp = self._client.chat.completions.create(**kwargs)  # 不支持时降级
        text = _extract_text(resp.choices[0].message)
        if not text.strip():
            raise ValueError(
                "Judge 返回空内容 finish_reason="
                f"{getattr(resp.choices[0], 'finish_reason', None)}"
            )
        return text

    async def a_generate(self, prompt: str) -> str:
        """异步生成（推荐 a_measure）。"""
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
                "Judge 返回空内容 finish_reason="
                f"{getattr(resp.choices[0], 'finish_reason', None)}"
            )
        return text

    def get_model_name(self) -> str:
        """DeepEval 展示用模型名。"""
        return str(self._model)


def new_session(prefix: str = "deepeval") -> str:
    """每次评测用新 session，避免记忆污染。"""
    return f"{prefix}__{uuid.uuid4().hex[:10]}"


def clip(text: str, n: int = 1200) -> str:
    """裁判输入过长易 JSON 截断，截断后再评。"""
    t = (text or "").strip()
    return t if len(t) <= n else t[:n] + "…"


async def get_app():
    """拿到已初始化 session store 的 AgentApplication。"""
    from application.services.agent_application import AgentApplication

    app = AgentApplication()
    if app.memory is None:
        await app.init_session_store()
    return app


def make_geval(
    *,
    name: str,
    criteria: str,
    threshold: float = 0.6,
    evaluation_params=None,
):
    """工厂：创建 GEval 指标（DeepEval 的 LLM-as-Judge）。

    criteria：用中文写「什么算好」。
    evaluation_params：告诉 GEval 看哪些字段（INPUT / ACTUAL_OUTPUT …）
    """
    from deepeval.metrics import GEval
    from deepeval.test_case import LLMTestCaseParams

    # 默认：看用户问题 + 模型实际输出
    params = evaluation_params or [
        LLMTestCaseParams.INPUT,
        LLMTestCaseParams.ACTUAL_OUTPUT,
    ]
    return GEval(
        name=name,  # 指标名，报告里显示
        criteria=criteria,  # 评分准则（GEval 核心）
        evaluation_params=params,  # 参与评分的字段
        threshold=threshold,  # 及格线 0~1
        model=DeepSeekJudge(),  # DeepSeek 裁判
        async_mode=True,  # 走 a_measure
    )


async def measure_ok(metric, case) -> float:
    """统一：a_measure → 打印 → assert；避免 assert_test（Windows GBK 易炸）。"""
    score = await metric.a_measure(case)
    print(
        f"[{getattr(metric, 'name', type(metric).__name__)}] "
        f"score={score} threshold={metric.threshold}"
    )
    print(f"reason={getattr(metric, 'reason', '')}")
    assert metric.is_successful(), (
        f"未通过: score={score}, reason={getattr(metric, 'reason', '')}"
    )
    return score


def sources_to_contexts(result) -> list[str]:
    """从 RunResult.meta['sources'] 抽出检索片段，供 Faithfulness 使用。"""
    meta = getattr(result, "meta", None) or {}
    sources = meta.get("sources") or []
    contexts: list[str] = []
    for s in sources[:5]:
        if isinstance(s, str) and s.strip():
            contexts.append(s.strip())
        elif isinstance(s, dict):
            # 常见字段：content / text / page_content
            for key in ("content", "text", "page_content", "snippet"):
                val = s.get(key)
                if isinstance(val, str) and val.strip():
                    contexts.append(val.strip())
                    break
            else:
                contexts.append(str(s)[:500])
        else:
            contexts.append(str(s)[:500])
    return contexts

def eval_root()->"Path":
    """测试根目录"""
    from pathlib import Path 
    return Path(__file__).resolve().parents[2] / "evals"
