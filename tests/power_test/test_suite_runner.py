# =============================================================================
# test_suite_runner.py
# 正式「完备」跑批入口：读 evals/suites，按环境变量过滤，断言 gate_pass。
#
# 用法（仓库根）：
#   $env:PYTHONIOENCODING="utf-8"
#   $env:EVAL_TAGS="p0"          # 只要带 p0 的题；空=全部
#   $env:EVAL_DOMAINS="E1,E6"    # 可选域过滤
#   pytest tests/power_test/test_suite_runner.py -v -s
# =============================================================================

from __future__ import annotations

import os

import pytest

from .eval_loader import load_suite
from .eval_runner import run_case, write_report


def _parse_set(env_name: str) -> set[str] | None:
    raw = (os.getenv(env_name) or "").strip()
    if not raw:
        return None
    return {x.strip() for x in raw.split(",") if x.strip()}


@pytest.mark.asyncio
async def test_eval_suite_gate():
    """P0/指定套件门禁：任一 case.gate_pass=False 则失败。"""
    tags = _parse_set("EVAL_TAGS") or {"p0"}  # 默认只跑 p0，避免一上来全量烧钱
    domains = _parse_set("EVAL_DOMAINS")

    cases = load_suite(tags_any=tags, domains=domains)
    assert cases, f"未加载到任何用例（tags={tags}, domains={domains}）。请先写 evals/suites/**/*.yaml"

    reports = []
    for case in cases:
        # 可用 EVAL_K 覆盖 YAML 里的 k（快速调试设 1）
        override_k = os.getenv("EVAL_K")
        if override_k:
            case.k = max(1, int(override_k))
        rep = await run_case(case)
        reports.append(rep)
        print(
            f"[GATE] {case.id} mode={case.pass_mode} "
            f"ok={rep.trials_ok}/{rep.k} gate={rep.gate_pass} attr={rep.attribution}"
        )

    path = write_report(reports, prefix="p0" if tags == {"p0"} else "suite")
    failed = [r for r in reports if not r.gate_pass]
    assert not failed, (
        f"{len(failed)} 题未过门禁；报告: {path}；"
        f"失败 id={[r.case_id for r in failed]}"
    )