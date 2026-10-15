# =============================================================================
# eval_runner.py
# 跑「单题一次」+「单题 k 次」+ Pass@k / Pass^k + 简单归因。
# 黑盒优先：通过 AgentApplication.use_cases / orchestrator，不直连 langchain。
# =============================================================================

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from deepeval.test_case import LLMTestCase, LLMTestCaseParams

from shared.timeutil import now_compact, now_iso

from .deepeval_harness import (
    clip,
    get_app,
    make_geval,
    new_session,
    sources_to_contexts,
)
from .eval_schema import EvalCase

_ROOT = Path(__file__).resolve().parents[2]
_REPORT_DIR = _ROOT / "evals" / "reports"


# ---------- 归因标签（报告里用；失败回流时按标签筛）----------
ATTR_RETRIEVAL = "retrieval"
ATTR_TOOL_SELECT = "tool_select"
ATTR_TRAJECTORY = "trajectory"
ATTR_HALLUCINATION = "hallucination"
ATTR_MEMORY = "memory"
ATTR_AUTH = "auth"
ATTR_TIMEOUT = "timeout"
ATTR_HARNESS = "harness"
ATTR_NONE = "ok"


@dataclass
class TrialResult:
    """一次尝试的结果（k 次中的 1 次）。"""

    ok: bool
    score: float | None = None
    reason: str = ""
    attribution: str = ATTR_NONE
    tools_called: list[str] = field(default_factory=list)
    answer_preview: str = ""
    error: str = ""


@dataclass
class CaseReport:
    """一条用例跑完 k 次后的汇总。"""

    case_id: str
    domain: str
    pass_mode: str
    k: int
    trials_ok: int
    pass_at_k: bool      # 至少一次成功
    pass_hat_k: bool     # 全部成功
    gate_pass: bool      # 按 pass_mode 决定的门禁结果
    trials: list[TrialResult] = field(default_factory=list)
    attribution: str = ATTR_NONE


def strip_open_tasks_footer(answer: str) -> str:
    """评测防御：去掉历史版本拼进正文的【未完成任务清单】后缀。"""
    if not answer:
        return ""
    marker = "【未完成任务清单】"
    idx = answer.find(marker)
    if idx < 0:
        return answer
    head = answer[:idx].rstrip()
    if head.endswith("---"):
        head = head[:-3].rstrip()
    return head


def check_expect_text(answer: str, case: EvalCase) -> tuple[bool, str]:
    """L0/L1：字符串级期望。返回 (是否通过, 原因)。"""
    text = answer or ""
    exp = case.expect

    # must_not_contain：出现任一违禁则 Fail
    for bad in exp.must_not_contain:
        if bad and bad in text:
            return False, f"包含禁止片段: {bad!r}"

    if not exp.must_contain:
        return True, "无 must_contain"

    if exp.match_any_of_must_contain:
        # 任一命中即可（安全拒答等多文案）
        if any(m and m in text for m in exp.must_contain):
            return True, "must_contain 任一命中"
        return False, f"must_contain 均未命中: {exp.must_contain}"

    # 默认：全部命中
    missing = [m for m in exp.must_contain if m and m not in text]
    if missing:
        return False, f"缺少必含片段: {missing}"
    return True, "must_contain 全部命中"


def match_tools(
    actual: list[str],
    expected: list[str],
    mode: str,
) -> tuple[bool, str]:
    """轨迹集合匹配（一期不看参数、不看严格顺序，除非 strict）。

    expected 为空时：
      - subset：无约束（兼容旧题）
      - strict / unordered / superset：要求 actual 也为空（零工具）
    """
    a = list(actual)
    e = list(expected)
    sa, se = set(a), set(e)

    if not expected:
        if mode in ("strict", "unordered", "superset"):
            ok = len(a) == 0
            return ok, f"{mode} 期望零工具: actual={a}"
        return True, "无轨迹期望"

    if mode == "subset":
        # subset = 期望工具都必须出现在实际中（允许额外工具）
        ok = se.issubset(sa)
        return ok, f"subset 期望⊆实际: expected={e} actual={a}"

    if mode == "superset":
        # 实际 ⊆ 期望：不许调用期望外的工具
        ok = sa.issubset(se)
        return ok, f"superset 实际⊆期望: expected={e} actual={a}"

    if mode == "unordered":
        ok = sa == se
        return ok, f"unordered 集合相等: expected={e} actual={a}"

    if mode == "strict":
        # 顺序也要一致（同名多次调用时按序列比）
        ok = a == e
        return ok, f"strict 序列相等: expected={e} actual={a}"

    return False, f"未知 match_mode={mode}"


def check_max_tool_calls(
    actual: list[str],
    max_calls: int | None,
) -> tuple[bool, str]:
    """工具调用次数上限（含同名多次）。"""
    if max_calls is None:
        return True, "无次数上限"
    n = len(actual)
    if n > max_calls:
        return False, f"工具调用次数超限: {n}>{max_calls} actual={actual}"
    return True, f"工具次数 OK: {n}<={max_calls}"


def extract_tool_names(result: Any) -> list[str]:
    """从 RunResult.meta 抽出工具名（agent 用例会写入 meta['tool_names']）。"""
    names: list[str] = []
    meta = getattr(result, "meta", None) or {}

    def _push(item: object) -> None:
        if isinstance(item, str) and item.strip():
            names.append(item.strip())
        elif isinstance(item, dict):
            n = item.get("tool") or item.get("name") or item.get("tool_name")
            if n:
                names.append(str(n))

    # 优先读评测友好字段
    for key in ("tool_names", "tools_called", "tools", "tool_calls"):
        val = meta.get(key)
        if isinstance(val, list):
            for item in val:
                _push(item)
    traces = getattr(result, "traces", None) or meta.get("traces") or []
    if isinstance(traces, list):
        for t in traces:
            _push(t)
    # 去重但保序（同一工具多次调用仍保留多次，供 strict；集合匹配用 set）
    return names



async def invoke_nexora(case: EvalCase) -> Any:
    """按 mode 调用应用层；返回 RunResult（或等价物）。

    这里用 use_cases，与现有 power_test 一致；也可改成 orchestrator.handle(RequestContext)。
    """
    from domain.run import RequestContext

    app = await get_app()
    inp = case.input
    sid = inp.session_id or new_session(case.id)

    # ---- 走统一编排（推荐，和 HTTP 主路径一致）----
    ctx = RequestContext(
        message=inp.message,
        mode=inp.mode,
        session_id=sid,
        tenant_id=inp.tenant_id,
        multi_mode=inp.multi_mode,
    )
    return await app.orchestrator.handle(ctx)


async def run_trial(case: EvalCase) -> TrialResult:
    """跑 1 次完整验证：调用 → L0/L1 → 轨迹 →（可选）Judge。"""
    try:
        result = await invoke_nexora(case)
    except Exception as exc:  # 调用失败：记 harness/timeout
        err = traceback.format_exc()
        attr = ATTR_TIMEOUT if "timeout" in str(exc).lower() else ATTR_HARNESS
        return TrialResult(ok=False, reason=str(exc), attribution=attr, error=err)

    answer = strip_open_tasks_footer(
        clip(getattr(result, "answer", None) or "")
    )
    tools = extract_tool_names(result)

    # 1) 确定性 / checklist
    ok_text, why_text = check_expect_text(answer, case)
    if not ok_text:
        return TrialResult(
            ok=False,
            reason=why_text,
            attribution=ATTR_AUTH if case.domain == "E14" else ATTR_HALLUCINATION,
            tools_called=tools,
            answer_preview=answer[:200],
        )

    # 2) 轨迹（集合/序列）
    ok_tr, why_tr = match_tools(
        tools,
        case.trajectory.expected_tools,
        case.trajectory.match_mode,
    )
    if not ok_tr:
        return TrialResult(
            ok=False,
            reason=why_tr,
            attribution=ATTR_TRAJECTORY,
            tools_called=tools,
            answer_preview=answer[:200],
        )

    # 2b) 调用次数上限
    ok_n, why_n = check_max_tool_calls(tools, case.trajectory.max_tool_calls)
    if not ok_n:
        return TrialResult(
            ok=False,
            reason=why_n,
            attribution=ATTR_TRAJECTORY,
            tools_called=tools,
            answer_preview=answer[:200],
        )

    # 3) deterministic / checklist：L0/L1 + 轨迹已过则不再花裁判费
    if case.judge.type in ("deterministic", "checklist"):
        return TrialResult(
            ok=True,
            score=1.0,
            reason=why_text or why_tr or why_n,
            tools_called=tools,
            answer_preview=answer[:200],
        )

    # 4) rubric_llm：GEval（二元门禁：is_successful）
    # RAG 可再加 Faithfulness：有 sources 才测（与现有 chat_modes 一致）
    metric = make_geval(
        name=f"ge_{case.id}",
        criteria=case.judge.criteria or "评估回答是否切题、准确、无明显胡编。",
        threshold=case.judge.threshold,
        evaluation_params=[
            LLMTestCaseParams.INPUT,
            LLMTestCaseParams.ACTUAL_OUTPUT,
        ],
    )
    tc = LLMTestCase(input=case.input.message, actual_output=answer)
    # 可选：把 retrieval context 塞进 test case（Faithfulness 时需要；GEval 可不用）
    _ = sources_to_contexts(result)

    try:
        # measure_ok 内部 assert；我们要 TrialResult，所以自己 a_measure
        score = await metric.a_measure(tc)
        ok = bool(metric.is_successful())
        reason = str(getattr(metric, "reason", "") or "")
        attr = ATTR_NONE if ok else ATTR_HALLUCINATION
        return TrialResult(
            ok=ok,
            score=float(score) if score is not None else None,
            reason=reason,
            attribution=attr,
            tools_called=tools,
            answer_preview=answer[:200],
        )
    except Exception as exc:
        return TrialResult(
            ok=False,
            reason=f"judge error: {exc}",
            attribution=ATTR_HARNESS,
            tools_called=tools,
            answer_preview=answer[:200],
            error=traceback.format_exc(),
        )


async def run_case(case: EvalCase) -> CaseReport:
    """跑 k 次，计算 Pass@k / Pass^k / gate_pass。"""
    k = max(1, int(case.k))
    trials: list[TrialResult] = []
    for i in range(k):
        print(f"=== case={case.id} trial={i+1}/{k} ===")
        trials.append(await run_trial(case))

    n_ok = sum(1 for t in trials if t.ok)
    pass_at_k = n_ok >= 1
    pass_hat_k = n_ok == k
    if case.pass_mode == "pass_at_k":
        gate = pass_at_k
    else:
        gate = pass_hat_k  # 默认业务可靠

    # 归因：优先取第一次失败的标签
    attr = ATTR_NONE
    for t in trials:
        if not t.ok:
            attr = t.attribution
            break

    return CaseReport(
        case_id=case.id,
        domain=case.domain,
        pass_mode=case.pass_mode,
        k=k,
        trials_ok=n_ok,
        pass_at_k=pass_at_k,
        pass_hat_k=pass_hat_k,
        gate_pass=gate,
        trials=trials,
        attribution=attr,
    )


def write_report(reports: list[CaseReport], *, prefix: str = "suite") -> Path:
    """把结果写成 JSON，便于 CI 归档 / 「完备」声明引用。"""
    _REPORT_DIR.mkdir(parents=True, exist_ok=True)
    # 文件名必须用 now_compact：now_iso 含 ':' / '+'，Windows 非法
    stamp = now_compact()
    path = _REPORT_DIR / f"{prefix}_{stamp}.json"
    payload = {
        "generated_at": now_iso(),
        "summary": {
            "total": len(reports),
            "gate_pass": sum(1 for r in reports if r.gate_pass),
            "gate_fail": sum(1 for r in reports if not r.gate_pass),
        },
        "cases": [asdict(r) for r in reports],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[eval_runner] report -> {path}")
    return path